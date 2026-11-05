"""Import B21 into disposable manager roots inside the workspace; never deploy."""
from package_native_v12 import ROOT, save_json
import audit_native_v16_import as importer

importer.W = ROOT / 'outputs/native-v29-b21-20261105'
if __name__ == '__main__':
    try:
        importer.main()
    except Exception as error:
        save_json(importer.W / 'package-inspection.json', dict(status='FAIL', error=str(error), gameDeployed=False))
        raise
