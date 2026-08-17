# Z Calibration Gate C — reboot recovery anomaly

**Date:** 2026-08-17  
**Issue:** #13 — `CALIBRATION-SUBSYSTEM-002`  
**Evidence class:** reboot/power-cycle recovery anomaly  
**Status:** OPEN / DIAGNOSTIC EVIDENCE ONLY  
**Authority:** does not authorize production Plugins AD5X motion or writes

## Trigger

A full printer power-cycle was performed after the prior clean Gate C evidence runs. The intended next step was a time-separated reboot/power-cycle repeatability run, but normal runtime recovery did not complete cleanly.

The printer remained on the same reserved LAN address `192.168.1.196`.

A Telegram startup notification was observed after reboot, showing that at least part of the post-boot software/network path executed. No conclusion is drawn about which exact component emitted it.

## External observations from the Windows client

### Network reachability

The printer responded on the expected reserved IP. TCP probes showed:

```text
22/tcp    accepts TCP
7125/tcp  accepts TCP
```

Port `8080` was later confirmed to be the camera HTTP service rather than Fluidd.

### Camera HTTP service

Request:

```text
GET http://192.168.1.196:8080/
```

Response:

```text
HTTP/1.0 200 OK
Server: MJPG-Streamer/0.2
```

This demonstrates that the camera HTTP service and basic network stack were responsive.

### Z-Mod static Fluidd HTTP service

Request:

```text
GET http://192.168.1.196/
```

Response:

```text
HTTP/1.1 200 OK
Server: Zmod httpd/1.1.0
Content-Type: text/html
```

The returned page was the Fluidd static `index.html`, including the expected built assets and custom IFS scripts. Therefore the Z-Mod static HTTP frontend server was responsive.

### Moonraker endpoint

Initial request:

```text
GET http://192.168.1.196:7125/server/info
```

Result:

```text
curl: (28) Operation timed out after 5002 milliseconds with 0 bytes received
```

A later retry with a 30-second client timeout did not recover normally. It ended after approximately `19.227 s` with:

```text
curl: (56) Recv failure: Connection was reset
```

Therefore TCP accept on `7125` did not imply a healthy Moonraker HTTP service.

### Dropbear SSH handshake

Windows OpenSSH connected to port `22` and received:

```text
Remote protocol version 2.0, remote software version dropbear_2019.78
```

The peers exchanged `SSH2_MSG_KEXINIT` and negotiated on the normal attempt:

```text
KEX:       curve25519-sha256
host key:  ecdsa-sha2-nistp256
cipher:    aes128-ctr
MAC:       hmac-sha2-256
```

The client then waited for:

```text
SSH2_MSG_KEX_ECDH_REPLY
```

and timed out. A second independent SSH attempt reproduced the same stall at the same protocol phase.

A third diagnostic attempt forced the alternate server host-key algorithm:

```text
HostKeyAlgorithms=ssh-rsa
```

The peers then negotiated:

```text
KEX:       curve25519-sha256
host key:  ssh-rsa
cipher:    aes128-ctr
MAC:       hmac-sha2-256
```

and again stalled while waiting for `SSH2_MSG_KEX_ECDH_REPLY`.

Therefore the failure is not specific to the ECDSA host-key path. Both ECDSA and RSA host-key selections fail before the server returns the key-exchange reply. The `curve25519-sha256` KEX path remains common to all observed SSH failures and has not yet been independently excluded.

All observed SSH failures occurred before user authentication. Therefore the evidence does not support a password/key/authorized-keys root cause.

## Current interpretation

The evidence supports a **partial post-power-cycle recovery failure**:

- IP/network reachability is present;
- the MJPG camera HTTP server responds normally;
- the Z-Mod static Fluidd HTTP server responds normally;
- Moonraker accepts TCP on `7125` but does not provide a healthy HTTP response;
- Dropbear accepts TCP, sends its banner, and begins SSH key exchange, but stalls before the server key-exchange reply;
- switching the SSH host-key algorithm from ECDSA to RSA does not change the failure;
- normal Fluidd operation is therefore unavailable because the static frontend cannot obtain a working Moonraker backend.

This evidence does **not yet establish the root cause**. Candidate mechanisms such as CPU starvation, storage/I/O stall, entropy/randomness starvation, blocked startup logic, service deadlock, a specific key-exchange path failure, or a Z-Mod/chroot recovery defect remain hypotheses only until directly distinguished.

## Gate C disposition

The intended reboot/time-separated repeatability measurement is **not started and not valid as a calibration run** while runtime recovery is abnormal.

No Z homing/probing, mesh mutation, Z-offset mutation, or Plugins AD5X production motion/write action should be performed until the runtime anomaly is understood or the printer returns to a clearly healthy baseline.

## Next diagnostic objective

Prefer non-mutating external tests first. In particular, distinguish whether the SSH failure follows the currently common `curve25519-sha256` key-exchange path by forcing an alternate KEX algorithm already advertised by Dropbear. If a read-only SSH path can be recovered, capture process state, load, memory, storage/I/O indicators, service process state, logs, and entropy availability before restarting services or power-cycling again.
