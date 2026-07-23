# Sembiotic

**The biological meaning platform. Powered by ARBITER.**

Sembiotic encodes biological objects once into a persistent 72-dimensional field, embeds only the incoming query, and ranks the complete field by deterministic coherence.

## Platform layers

- Omics and molecular state
- Imaging and phenomics
- Cell systems and models
- Pathways, perturbations, assays, and controls
- Experiment design and GeneQuery interpretation
- Translational evidence and profile-to-model matching
- Laboratory operations, quality, cold chain, and CAPA
- Private enterprise fields, APIs, and biological data products

## Local runtime

- Field server: `http://127.0.0.1:8799`
- Query embedding: `http://127.0.0.1:8000/v1/embed`
- Production hostname: `https://sembiotic.actualgeneralintelligence.com`

The public site and field API are served by the same local runtime through the dedicated Cloudflare tunnel.
