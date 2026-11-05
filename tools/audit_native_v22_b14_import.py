"""Guarded B14 isolated imports; never deploy to the game."""
from package_native_v12 import ROOT,save_json
import audit_native_v16_import as importer
importer.W=ROOT/'outputs/native-v22-b14-20261104'
if __name__=='__main__':
    try:importer.main()
    except Exception as error:
        save_json(importer.W/'package-inspection.json',dict(status='FAIL',error=str(error),gameDeployed=False))
        raise
