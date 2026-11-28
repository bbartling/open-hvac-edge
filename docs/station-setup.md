# Running bask-223p against a Niagara station (read-only)

Install the signed `baskStream-rt.jar` from [rbhans/bask-stream](https://github.com/rbhans/bask-stream)
(the jar at the repository root is API 1.12) into the Niagara `modules` folder, restart the
station, and add `BASkStreamService` from the `baskStream` palette. Confirm `servletName` is
`stream`.

Set these on the service (all exist in API 1.12):

- `writesEnabled` = false (the default is true)
- `modelEditsEnabled` = false, `securityEditsEnabled` = false
- `allowedPathPatterns` = `slot:/Drivers/**` (the default is `slot:/*`; `slot:/Drivers/*` matches children only and does not include the Drivers folder itself). To also browse the Drivers folder node, add `slot:/Drivers` as a second pattern.
- a dedicated station user with read-only rights on Drivers
- optional `requireAuthorizationHeader` = true (then pass `--ws-auth-header` to `export-223p`)

**What to map.** On live HVAC systems, do not map or poll every BACnet point.
A full object list plus present-value polling bottlenecks easily on IoT links
and especially on legacy MS/TP networks. Proxy only the points the 223P model
and the application need. Mapping every object on the bench FEC (device 5007)
is a test-bench exception for this tool, not recommended practice on production
stations.

`agentPointWrites`, agent profiles, and `resolve` arrive in API 1.13/1.14. This client gates
those operations on the station's `capabilities` reply, so it also works against a 1.12 station.

Check `https://<station>/stream/health` after login: the JSON should report `apiVersion`. Then:

```powershell
bask-223p export-223p --station https://localhost --insecure `
  --env-file path/to/station.env --base https://example.org/lab `
  --save-snapshot outputs/station/snapshot.json --out outputs/station/site-223p.ttl
```

The env file holds `NIAGARA_USER` and `NIAGARA_PASS`. Values are never printed.

To join the export with a direct BACpypes3 scan:

```powershell
bask-223p reconcile --niagara outputs/station/site-223p.ttl --scan path/to/site-scan.ttl --out outputs/reconcile
```
