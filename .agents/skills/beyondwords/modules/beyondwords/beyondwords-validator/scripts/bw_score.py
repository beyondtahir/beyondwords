#!/usr/bin/env python3
"""Retired sellability score; boolean preferences cannot establish book success."""
import json
import sys


def score(cfg):
    return {'tool':'bw_score','version':'1.1.0','ok':False,'status':'NEEDS_REVIEW','total':None,
            'verdict':'UNKNOWN','publicationReady':False,
            'missingEvidence':['Source-linked market observations','Validated reader and buyer needs','Independent editorial evaluation','Real-reader evaluation','Verified costs and budget'],
            'fixes':['Use the BP-002 research brief; keep observed facts separate from hypotheses.'],
            'handoff':{'schema':'beyondwords-project/1.0','verdicts':{'sellability':None,'sellabilityVerdict':'UNKNOWN'},'note':'No readiness or success score is available.'}}


if __name__=='__main__':
    print(json.dumps(score(json.loads(sys.argv[1] if len(sys.argv)>1 else sys.stdin.read())),indent=2))
