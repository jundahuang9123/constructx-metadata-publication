# Credits

This work builds on:

- Florian Hoelken et al., Semantic Data Catalog for decentralized Solid-based dataspaces
- TMDT / University of Wuppertal
- Repository: `https://github.com/tmdt-buw/semantic-data-catalog`
- License: Apache-2.0

## Adapted Ideas

| Source | Use in this repository |
| --- | --- |
| Solid-OIDC session handling concepts | Browser login/session flow through Inrupt authn client |
| Solid catalogue path conventions | WebID-to-`catalog/cat.ttl` inference |
| WebID and registry conventions | Participant identity shown and pushed to the central catalogue |
| DCAT modelling choices | RDF preview extracts `dcat:Catalog`, `dcat:Dataset`, and `dcat:Distribution` |
| UI concepts | Step-based catalogue operator workflow and preview/result panels |

No large source files are copied wholesale. Where code is directly adapted, files carry an attribution header.

