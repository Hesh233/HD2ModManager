"""Use the manager's protected importer only in disposable B13 libraries."""
from package_native_v12 import ROOT,save_json
import audit_native_v16_import as importer
importer.W=ROOT/'outputs/native-v21-b13-20261104'
if __name__=='__main__':
    try:importer.main()
    except Exception as error:
        save_json(importer.W/'package-inspection.json',dict(status='FAIL',error=str(error),gameDeployed=False))
        raise
