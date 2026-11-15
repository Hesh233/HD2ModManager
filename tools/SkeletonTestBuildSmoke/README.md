# Skeleton-test build UI regression

Loads the actual GUI DLL with each installation's own preserved dependencies. No production startup, Window/Show/ShowDialog, network request, library import, Python execution, or game deployment.

- `audit <before-program> <candidate> <report.json>`: symbolic IL scope (startup/build-policy/updater/update-card only), unchanged assembly identity/references, update-card-only BAML changes, DLL/portable-PDB pairing.
- `headless <candidate> <output>`: exact startup text and callback/owner/idle scheduling, dynamic version from the actual GUI assembly rather than the test entry host, existing AutoCheck/AutoUpdate=true and cached newer release kept inert, every update command/preferences setter safe even through direct invocation, old result/ZIP/part files byte-preserved, and the actual settings card at 780/500/320px.

Headless mode must run from a fresh executable directory containing `SMOKE-SANDBOX.marker`. Its config/cache writes are test fixtures only. Never run the production manager just to inspect the notice; startup may synchronize/deploy the user's active library. Actual modal-dialog/game behavior remains for the user to confirm after restarting.

When merging upstream later, keep `SkeletonTestBuild` and its updater/UI guards. Change the main GUI project Version to the new base version; the settings label automatically follows it.

Safety: never pump the Dispatcher after constructing the actual App for resources. WPF queues startup in the Application constructor even without Run. Fixtures explicitly pin game/library paths to empty sandbox directories, and the successful suite requires no MainWindow and no startup log. Preserve failed sandboxes for audit.
