"""Inspect and import only B6 and the v15 animation into disposable libraries."""
import audit_native_v12_import as audit
from package_native_v15 import ROOT,W
audit.ROOT=ROOT;audit.WORK=W

if __name__=='__main__':
    try:audit.main()
    except Exception as error:
        audit.save_json(W/'package-inspection.json',dict(status='FAIL',error=str(error),gameDeployed=False));raise
