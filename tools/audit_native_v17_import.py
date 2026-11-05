"""Run the existing guarded, non-deploying import audit on B8 only."""
from package_native_v12 import ROOT,save_json
import audit_native_v16_import as audit
audit.W=ROOT/'outputs/native-v17-20261104'


if __name__=='__main__':
    try:audit.main()
    except Exception as error:
        save_json(audit.W/'package-inspection.json',dict(status='FAIL',error=str(error),gameDeployed=False))
        raise
