# Sembiotic

**The biological meaning platform. Powered by ARBITER.**

Sembiotic encodes biological objects once into a persistent 72-dimensional field, embeds only the incoming query, and ranks the complete field by deterministic coherence.

## Product identity

- **Sembiotic** is the platform.
- **ARBITER** is the deterministic measurement engine.
- **72D frozen geometry** is the technical layer.
- Instrument Sans carries the editorial identity; Fragment Mono carries field metadata and system state.
- The homepage uses an original biological-field gallery rather than stock photography or synthetic AI imagery.

## Platform layers

- Experiment systems and catalog resolution
- GeneQuery interpretation
- Omics and molecular state
- Imaging and phenomics
- 72D biological asset retrieval
- Translational evidence and profile-to-model matching
- Laboratory operations, quality, cold chain, and CAPA
- Platform, portfolio, partnership, and licensing decisions

## Local runtime

- Field server: `http://127.0.0.1:8799`
- Query embedding: `http://127.0.0.1:8000/v1/embed`
- Production hostname: `https://sembiotic.actualgeneralintelligence.com`

The public site and field API are served by the same local runtime through the dedicated Cloudflare tunnel.

## Deploy

```zsh
./DEPLOY_SEMBIOTIC.command
```

The deploy command validates the HTML and JavaScript, commits to `ziolndr/sembiotic`, restarts the persistent field service, and verifies the public hostname.
