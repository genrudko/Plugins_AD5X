# Z Calibration Gate C — reboot recovery anomaly

**Date:** 2026-08-17  
**Issue:** #13 — `CALIBRATION-SUBSYSTEM-002`  
**Evidence class:** reboot/power-cycle recovery anomaly  
**Status:** RECOVERED ON SUBSEQUENT COLD BOOT / ROOT CAUSE OPEN / DIAGNOSTIC EVIDENCE ONLY  
**Authority:** does not authorize production Plugins AD5X motion or writes

## Trigger

A full printer power-cycle was performed after the prior clean Gate C evidence runs. The intended next step was a time-separated reboot/power-cycle repeatability run, but normal runtime recovery did not complete cleanly.

The printer remained on the same reserved LAN address `192.168.1.196`.

A Telegram startup notification was observed after the anomalous reboot, showing that at least part of the post-boot software/network path executed. No conclusion is drawn about which exact component emitted it.

## External observations during the anomalous boot

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

A fourth diagnostic attempt forced an alternate KEX algorithm already advertised by Dropbear:

```text
KexAlgorithms=diffie-hellman-group14-sha256
```

The peers negotiated:

```text
KEX:       diffie-hellman-group14-sha256
host key:  ecdsa-sha2-nistp256
cipher:    aes128-ctr
MAC:       hmac-sha2-256
```

The client again stalled waiting for the server key-exchange reply.

Therefore the failure is not specific to the ECDSA host-key path, RSA host-key path, or the `curve25519-sha256` KEX path. All observed SSH failures occurred before user authentication, so the evidence does not support a password/key/authorized-keys root cause.

### Stock FlashForge network ports during the anomalous state

External TCP probes showed:

```text
8898/tcp  closed
8899/tcp  closed
```

Therefore the stock FlashForge network-control path was not available as an alternate recovery channel in the observed anomalous state.

## Subsequent cold-boot recovery observation

The printer was then powered off again and left unpowered for a longer interval before the next power-on. The owner explicitly observed that this off interval was longer than during the preceding failed recovery attempt.

A Windows boot watcher was started before power-on. It monitored ICMP, TCP ports `22`, `80`, `443`, `7125`, `8080`, `8898`, `8899`, HTTP service responses and SSH key exchange without issuing printer-control commands.

Watcher start / owner power-on prompt:

```text
10:45:56.743  NOW POWER ON THE PRINTER
```

Observed boot timeline:

```text
10:45:57.085  PING DOWN
10:45:57.354  TCP 22 CLOSED
10:45:57.609  TCP 80 CLOSED
10:45:57.860  TCP 443 CLOSED
10:45:58.113  TCP 7125 CLOSED
10:45:58.366  TCP 8080 CLOSED
10:45:58.618  TCP 8898 CLOSED
10:45:58.871  TCP 8899 CLOSED

10:48:16.094  TCP 8899 OPEN
10:48:16.450  PING UP rtt=1ms
10:48:16.455  TCP 22 OPEN
10:48:16.458  TCP 80 OPEN
10:48:16.711  TCP 7125 OPEN
10:48:18.365  HTTP 80 -> HTTP/1.1 200 OK
10:48:18.385  MOONRAKER 7125 -> HTTP/1.1 200 OK
10:48:19.491  SSH 22 -> KEX_OK

10:49:00.069  TCP 8080 OPEN
10:49:03.036  CAMERA 8080 -> HTTP/1.0 200 OK

10:49:48.683  TCP 8899 CLOSED
```

Relative to the watcher power-on prompt, the first observed stock `8899` listener appeared after approximately `139.35 s`; ICMP, SSH, Z-Mod HTTP and Moonraker followed within about `0.62 s`. Healthy Z-Mod HTTP and Moonraker HTTP responses were observed at approximately `141.62-141.64 s`, and a complete SSH key exchange succeeded at approximately `142.75 s`.

The camera HTTP service appeared materially later, at approximately `183.33 s`, with a successful HTTP response at approximately `186.29 s`.

Port `8898` did not open during the watcher interval. Port `8899` opened early in the responsive phase and later closed at `10:49:48.683`; this transient behavior is retained as raw boot evidence and is not interpreted as a fault by itself.

The watcher logged repeated `PING UP` lines when RTT changed because the probe state string included the RTT value. Those lines are not repeated state transitions and have no diagnostic meaning beyond continued ICMP reachability.

## Current interpretation

The evidence establishes two distinct outcomes across consecutive power cycles:

1. one boot reached only a **partial recovery state**, where static/lightweight HTTP services were responsive but Moonraker and SSH could not complete normal request/handshake processing;
2. a subsequent cold boot after a longer unpowered interval reached a **healthy network/runtime state**, including Moonraker HTTP `200 OK` and successful SSH key exchange.

The longer unpowered interval is therefore a real correlating condition, but it is **not yet a proven cause**. It would be premature to claim capacitor discharge, IFS state, IFS back-powering, peripheral MCU state, storage/I/O recovery, entropy availability, or any other mechanism without direct evidence.

The successful boot timeline also shows that this AD5X can take roughly `2 min 20 s` before its main network/runtime services first become reachable after a cold start. That timing does not explain the preceding anomaly by itself, because the anomalous state persisted through repeated later probes rather than merely being checked too early.

IFS-related software/hardware remains one candidate because the current machine composition includes Z-Mod IFS handling and Plugins AD5X IFS work, but this event does **not** establish IFS causality. No component is assigned root cause at this stage.

## Gate C disposition

The failed recovery event itself is **not a calibration run** and does not count as Gate C repeatability evidence.

The subsequent cold boot restored a usable baseline, but the intended reboot/time-separated calibration measurement has still not started. Before any Z homing/probing or calibration motion, capture the recovered live runtime state and relevant logs/process/resource evidence, then perform a fresh clean preflight.

No production Plugins AD5X motion or write gate is opened by this evidence.

## Next diagnostic objective

While SSH and Moonraker are healthy, capture the current successful-boot process/resource state and persistent logs before another restart or calibration action. The highest-value observations are:

- uptime/load/memory;
- filesystem usage and basic kernel messages;
- entropy availability;
- process list, especially Moonraker/Klipper/Z-Mod/IFS-related processes;
- listening sockets where available;
- recent Moonraker and Klipper logs;
- current Moonraker/Klipper readiness.

Only after preserving that evidence should the time-separated Gate C measurement resume.
