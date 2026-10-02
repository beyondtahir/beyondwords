#!/usr/bin/env python3
"""Compatibility endpoint: competitor sales cannot be inferred from BSR.

The unvalidated default curve, country multipliers and calibration confidence
were removed. Actual sales reporting is a later milestone, not a BP-002 claim.
"""
import json
import sys


def estimate(bsr=None, **kwargs):
    error = 'BSR-to-sales inference is unavailable; no validated model or sales evidence exists.'
    if kwargs.get('rank_type') == 'subcategory': error = 'subcategory rank cannot establish sales. ' + error
    return {'tool':'bw_sales','version':'1.1.0','ok':False,'status':'UNAVAILABLE',
            'error':error,'estSalesPerDay':None,'estimatedRoyalties':None,'successProbability':None,
            'nextAction':'Use verified, authorized account sales reports for actual sales. Never derive competitor income from rank.'}


def main():
    args=sys.argv[1:]
    rank_type=args[args.index('--rank-type')+1] if '--rank-type' in args and args.index('--rank-type')+1<len(args) else None
    print(json.dumps(estimate(rank_type=rank_type),indent=2))


if __name__=='__main__':main()
