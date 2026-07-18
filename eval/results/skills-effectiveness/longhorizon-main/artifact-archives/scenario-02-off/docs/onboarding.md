# Onboarding

Run streaming onboarding for the operations owner with up to three jobs in parallel, processing the `new` queue before `recovery`:

```sh
onboard run --config config/onboarding.json --mode streaming --max-parallel 3 --owner operations --queue new --queue recovery
```
