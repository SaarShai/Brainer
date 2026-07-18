# Onboarding

Run onboarding in streaming mode for the operations owner, processing the `new` queue before `recovery` with up to three jobs in parallel:

```sh
onboarding run \
  --config config/onboarding.json \
  --mode streaming \
  --max-parallel 3 \
  --owner operations \
  --queue new \
  --queue recovery
```
