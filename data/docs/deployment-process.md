# Deployment Process

## Branches and reviews

All changes go through a pull request into `main`. Every pull request needs one approving review and a green CI run. Changes to payment code need two reviews.

## Release schedule

Production deployments happen Monday to Thursday between 9:00 and 16:00. There are no deployments on Fridays, on public holidays or during the code freeze from 20 November to 2 December, which covers Black Friday and Cyber Monday.

## Staging

Every merge to `main` deploys to staging automatically. Production deployments are started manually from the pipeline after a check on staging.

## Database migrations

Migrations must be backwards compatible with the previous release, so that a rollback of the application never needs a database rollback. Columns are removed only in a later release after the code that used them is gone.

## Feature flags

New features that customers see ship behind a feature flag. Flags are removed within 30 days after the feature is fully enabled.
