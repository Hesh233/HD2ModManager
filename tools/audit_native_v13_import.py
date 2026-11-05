"""Use the unchanged import contract against v13 packages and isolated libraries."""
import audit_native_v12_import as audit
from package_native_v13 import ROOT, WORK

audit.ROOT=ROOT
audit.WORK=WORK

if __name__=='__main__':
    try:
        audit.main()
    except Exception as error:
        audit.save_json(WORK/'package-inspection.json',dict(status='FAIL',error=str(error),gameDeployed=False))
        raise
