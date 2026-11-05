"""Protected isolated H/W imports, with no game deployment."""
from package_native_v12 import ROOT,save_json
import audit_native_v16_import as importer
importer.W=ROOT/'outputs/native-v24-b16-20261105'
if __name__=='__main__':
    try:importer.main()
    except Exception as error:
        save_json(importer.W/'package-inspection.json',dict(status='FAIL',error=str(error),gameDeployed=False))
        raise
