"""Reuse the guarded importer against only the new B12 diagnostic packages."""
from package_native_v12 import ROOT,save_json
import audit_native_v16_import as importer
importer.W=ROOT/'outputs/native-v20-b12-20261104'
if __name__=='__main__':
    try:importer.main()
    except Exception as error:
        save_json(importer.W/'package-inspection.json',dict(status='FAIL',error=str(error),gameDeployed=False))
        raise
