# Punch list: first live export and reconcile

What is already done in this repository, and what you still need to do on the
station and the bench. Nothing in this tool writes to the station.

## Already done

1. The signed upstream `baskStream-rt.jar` (API 1.12) is staged in a temp folder
   with `INSTALL.md` and a jarsigner verification. See [station-setup.md](station-setup.md).
2. The read-only client and `export-223p` work against API 1.12 (the signed jar)
   and API 1.14 (source). 1.13/1.14-only operations such as `resolve` are gated on
   `capabilities` and are refused locally on 1.12.
3. BACnet references use `bacnet://<device>/<type>,<instance>`. Worker Pi 1 runs
   the BACpypes3 driver against the configured points. `reconcile` joins that
   TTL with the Niagara TTL (or with an external scan CSV).
4. Official 223P SHACL was run against the bundled AHU snapshot (`223p.ttl` shapes):
   **0 Violations**. Warnings that an `ObservableProperty` has no `s223:Sensor`
   `observes` it are expected for an external-reference graph.
5. Unit tests for discovery, export, reconcile, and the 1.12/1.14 fake station
   pass locally.

## You need to do

1. **Install the signed jar and restart** (this is the one restart).
   Stop the station, copy `baskStream-rt.jar` into the Niagara 4.15 `modules`
   folder, start the station, and restart Workbench so the palette appears.
   There is no `baskStream-ux.jar` for 1.12; the API does not need one.
2. **Add `BASkStreamService`** from the `baskStream` palette to Config → Services.
   Confirm `servletName` is `stream`.
3. **Read-only service settings** (all exist in 1.12):
   - `writesEnabled` = false (it defaults to true; change it)
   - `modelEditsEnabled` = false, `securityEditsEnabled` = false (defaults)
   - `allowedPathPatterns` = `slot:/Drivers/**` (default is `slot:/*`; add `slot:/Drivers` as well if you need the Drivers folder node itself)
   - optional `requireAuthorizationHeader` = true (then pass `--ws-auth-header`
     to `export-223p`)
   Save the station.
4. **Create a dedicated read-only station user** with permission to browse and
   read under Drivers. Put `NIAGARA_USER` and `NIAGARA_PASS` in a local env file
   that is not committed (for example `path/to/station.env`).
5. **Discover and add BACnet proxy points** under the BacnetNetwork for **both**
   bench devices, into each device's Points folder (or the network Points
   extension). No Haystack tagging is required for `export-223p`. On live HVAC
   systems, map only the points you need; a full object list plus polling can
   bottleneck IoT links and legacy MS/TP trunks. A complete mapping of the bench
   FEC (device 5007) is a test-bench exception, not production practice.
6. **Check** `https://localhost/stream/health` after login: JSON should report
   `apiVersion` 1.12. Then run:

   ```powershell
   python -m bask_223p export-223p --station https://localhost --insecure `
     --env-file path/to/station.env --base https://example.org/lab `
     --save-snapshot outputs/station/snapshot.json `
     --validate-out outputs/station/validate `
     --shapes path/to/223p.ttl `
     --out outputs/station/site-223p.ttl
   ```

7. **Run a BACpypes3 BACnet-to-RDF scan** for the same two devices. The Niagara
   process on this PC already holds **UDP 47808**, so do the scan from **another
   machine**, or temporarily stop the station if you must scan from this PC.
   Do not scan against a live station UDP port from the same host while it is
   bound. Keep the scan TTL/CSV out of git if it contains site addresses.
8. **Reconcile** the Niagara export with the scan:

   ```powershell
   python -m bask_223p reconcile --niagara outputs/station/site-223p.ttl `
     --scan path/to/site-scan.ttl --out outputs/reconcile `
     --merged-out outputs/reconcile/merged.ttl
   ```

   Expect rows: `matched`, `missing_in_niagara` (in the scan, no Niagara proxy),
   `missing_in_scan` (Niagara points at an object the scan did not see).
9. **Check SHACL results** in `outputs/station/validate/official-223p-shacl.json`
   (no Violations) and the reconcile summary. Then share those two outputs
   (redact any host addresses first).
10. Rollback if needed: stop the station, remove the jar from `modules`, restart.

A later optional step is to author a full 223 topology (sensors, connection
points, equipment subclasses) from reviewed templates and re-validate the
closure with OntoEnv + Shifty. That work is out of scope for the first export.
