# Incident Response

## Severity levels

SEV1 means the shop or checkout is down for all customers. SEV2 means a major feature is broken or degraded, for example payments fail for one provider. SEV3 covers minor bugs with a workaround.

## Who responds

The on-call engineer acknowledges a page within 15 minutes. For SEV1 the on-call engineer becomes incident commander until handing over, opens the incident channel and posts an update for support every 30 minutes.

## First steps

Check the status dashboard and recent deployments first. If a deployment in the last two hours touched the affected service, roll it back before investigating further. Rolling back is always allowed without approval during an incident.

## Communication

Customer facing status updates are written by support, not by engineers. Engineers give support a plain description of impact and expected recovery time.

## Postmortems

Every SEV1 and SEV2 incident gets a blameless postmortem within 5 working days. It lists the timeline, root cause, what went well and action items with owners.

## On call rotation

The rotation lasts one week and changes on Monday at 10:00. On call engineers receive a fixed allowance per week and compensation time for pages outside working hours.
