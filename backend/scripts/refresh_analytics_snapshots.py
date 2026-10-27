"""Explicit refresh; run from backend: python -m scripts.refresh_analytics_snapshots --all."""
import argparse
from datetime import date
from sqlalchemy import or_

from app.database.session import SessionLocal
from app.models.instrument import InstrumentUnit
from app.services.analytics_snapshots import create_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--all', action='store_true')
    group.add_argument('--instrument-id', type=int, action='append')
    parser.add_argument('--as-of', type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    if args.as_of > date.today(): parser.error('--as-of cannot be in the future')
    with SessionLocal() as db:
        query = db.query(InstrumentUnit).order_by(InstrumentUnit.id)
        if args.all:
            query = query.filter(or_(InstrumentUnit.lifecycle_state.is_(None), InstrumentUnit.lifecycle_state != 'retired'))
        else:
            query = query.filter(InstrumentUnit.id.in_(args.instrument_id))
        instruments = query.all()
        if not args.all and {i.id for i in instruments} != set(args.instrument_id):
            parser.error('Some instrument IDs do not exist; no snapshots created')
        for instrument in instruments:
            result = create_snapshot(db, instrument, args.as_of)
            print(f'instrument={instrument.id} snapshot={result.id} score={result.score_status} risk={result.risk_status}')


if __name__ == '__main__': main()
