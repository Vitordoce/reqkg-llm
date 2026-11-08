# Issue #5114: Add support for CCSDS security protocol (encryption/authentication)

- Fonte: https://github.com/nasa/fprime/issues/5114
- Autor (pseudonimizado): stakeholder-02
- Estado na coleta: closed

| | |
|:---|:---|
|**_F´ Version_**| |
|**_Affected Component_**|  |
---
## Feature Description

The [Space Data Link Security (SDLS) protocol](https://ccsds.org/Pubs/355x0b2.pdf) is a CCSDS standard for encryption/authentication of comms. It basically encrypts space packets and sends them over TC/TM/AOS.

Encryption/authentication is now very much of a requirement for most mission. F Prime must support it out of the box.

## Comentários

### Comentário 1 (stakeholder-07)

SDLS support (AES-256-GCM `AESEncryptor` / `AESDecryptor`) landed in #5795 (merged 2026-09-10). Recommend closing; follow-up hardening is tracked in #5931.

[Written by Devin](https://nasa-jpl-demo.devinenterprise.com/sessions/83546cf842f144298a0b6a302e0cb6d4)
