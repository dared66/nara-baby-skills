"""Bottle payloads and one-operation logging with semantic readback."""
from decimal import Decimal, InvalidOperation
import hashlib
import json
import time

from nara_keychain import NaraError


def bottle_fields(amount, breast_milk=True, formula_name=None):
    try:
        volume = Decimal(str(amount))
        if not volume.is_finite() or volume <= 0 or volume > Decimal('1000000'):
            raise ValueError
        scaled = volume * 10
        if scaled != scaled.to_integral_value():
            raise ValueError
    except (InvalidOperation, ValueError):
        raise NaraError('Bottle amount must be positive fluid ounces in increments of 0.1; no rounding is applied.') from None
    if not isinstance(breast_milk, bool):
        raise NaraError('Specify breast milk or formula explicitly.')
    if breast_milk and formula_name:
        raise NaraError('A formula name cannot be used for a breast-milk bottle.')
    # App-created 2.5 fl oz record: Num=25, Exp=1, not Num=250.
    number = int(scaled)
    fields = dict(feedType='BOTTLE', bottleTypeBreastMilk=breast_milk,
                  bottleTypeFormula=not breast_milk, bottleVolumeNum=number,
                  bottleVolumeExp=1, bottleVolumeUnit='FLOZ',
                  bottleVolume=number, bottleVolumeBase=number)
    prefix = 'bottleBreastMilkVolume' if breast_milk else 'bottleFormulaVolume'
    fields.update({prefix+'Num': number, prefix+'Exp': 1, prefix+'Unit': 'FLOZ'})
    if formula_name:
        fields['formulaName'] = formula_name
    return fields


def decoded_volume(record, prefix='bottleVolume'):
    num, exp = record.get(prefix+'Num'), record.get(prefix+'Exp')
    if (isinstance(num, bool) or not isinstance(num, (int, float)) or
            isinstance(exp, bool) or not isinstance(exp, int) or not 0 <= exp <= 6 or
            record.get(prefix+'Unit') != 'FLOZ'):
        raise NaraError('Bottle volume has an unsupported or incomplete encoding.')
    value = Decimal(str(num)) / (10 ** exp)
    if not value.is_finite() or value <= 0:
        raise NaraError('Bottle volume is invalid.')
    return value


def log_bottle(api, *, child, begin, amount, breast_milk, formula_name=None, check_only=False):
    fields = bottle_fields(amount, breast_milk, formula_name)
    expected = dict(fields, childKey=child, type='FEED', beginDt=begin, tz=api.activity_timezone)
    scope = json.dumps([api.family_key, child, begin, 'BOTTLE'], separators=(',', ':'))
    track_id = 'bottle' + hashlib.sha256(scope.encode()).hexdigest()[:32]

    def matches(record):
        return (isinstance(record, dict) and
                record.get('familyKey', api.family_key) == api.family_key and
                all(record.get(k) == v for k, v in expected.items()))

    def receipt(record, status):
        prefix = 'bottleBreastMilkVolume' if breast_milk else 'bottleFormulaVolume'
        volume = decoded_volume(record)
        if volume != Decimal(str(amount)) or decoded_volume(record, prefix) != volume:
            raise NaraError('Bottle readback does not match the requested amount.')
        return dict(status=status, verified=True, amount=format(volume.normalize(), 'f'),
                    unit='fl oz', milk='breast milk' if breast_milk else 'formula',
                    track=record)

    tracks = api.get_data()
    candidates = [(key, record) for key, record in tracks.items()
                  if record.get('childKey') == child and record.get('type') == 'FEED'
                  and record.get('feedType') == 'BOTTLE' and record.get('beginDt') == begin]
    if candidates:
        if len(candidates) == 1 and matches(candidates[0][1]):
            return receipt(candidates[0][1], 'already_recorded')
        raise NaraError('A bottle already exists at that time with different or ambiguous details. Inspect it; do not create another.')
    if track_id in tracks:
        raise NaraError('The stable activity ID is already in use. Inspect it; do not replace it.')
    if check_only:
        return dict(status='not_found', verified=False)
    if getattr(api, '_selected_child', None) != child or not getattr(api, '_allow_writes', False):
        raise NaraError('A selected child and authorized write client are required.')
    # Preselected deterministic ID survives process failures. Never retry a write here.
    try:
        api.log_activity('FEED', begin_dt=begin, track_id=track_id, **fields)
    except Exception:
        pass  # Submission can succeed despite a lost response; inspect the same ID.
    for attempt in range(3):
        try:
            fresh = api.get_data().get(track_id)
            if matches(fresh):
                return receipt(fresh, 'saved')
        except Exception:
            break
        if attempt < 2:
            time.sleep(0.25)
    raise NaraError('Bottle outcome is uncertain. Check the same time with --check-only; do not retry a write or create a replacement.')
