# ontology_windfarm

Microsoft's complete WindFarm sample of an ontology definition (generation 2, TMDL): the 35 parts of the JSON example in
the section "Full WindFarm ontology definition example" of
`tools/Fabric.Mcp.Tools.Docs/src/Resources/item-definitions/ontology-definition.md` in github.com/microsoft/mcp at
commit `7257a94355dd63ba4f1ba43fc5ae5dfcd1a7203d`, read on 2 November 2026.

- `parts/` holds each part's payload, base64-decoded and otherwise unmodified, at the part's own path (the TMDL files
  keep their CRLF line ends; `.gitattributes` keeps git from changing them).
- `parts.json` lists the parts in the example's order with their payload type and the SHA-256 of the decoded bytes.
- `LICENSE-microsoft-mcp.txt` is the `LICENSE` file of that repository at that commit (MIT, Copyright (c) Microsoft
  Corporation).

`tests/test_ontology_windfarm.py` checks the files against `parts.json` and compares their structure with what
`fabric_backend.ontology.ontology_parts` writes; the differences it records are listed there and are not changed in the
writer until they have been tried in Fabric. The sample's expression names a SQL analytics endpoint host and a database
id; both are Microsoft's, from the published sample, and are not used anywhere else in this repository.
