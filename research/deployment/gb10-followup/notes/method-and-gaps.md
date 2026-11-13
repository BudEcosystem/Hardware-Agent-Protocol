# Method, conflicts and remaining work

The selected source unit is each published page's primary content. NVIDIA docs
use `article.bd-article`; navigation, legal footers and linked pages are outside
the reading unit. Footer dates were inspected separately and retained in
source-status.json. Full raw HTML remains available for reproduction. Tables
are preserved as row/cell arrays to avoid treating flattened text as row order.
All eight tables were inspected against those arrays. The single material
figure was opened at readable resolution; it labels power, three additional
USB-C ports, HDMI, Ethernet and two QSFP ports.

The vLLM page's empty `main` is a streaming placeholder. The complete page is
in the raw response's server-streamed `div#S:f`, containing the exact advanced
tab heading. The first empty one-line extraction and original manifest are
retained in `text/vllm-advanced.txt` and
`notes/acquisition-before-stream-extraction.jsonl`. The reading record points
to the corrected nonempty streamed extraction. No script was evaluated.

Web discovery returned a redirect for unversioned porting pages. The selected
URLs use the observed `/latest/` targets. The web tool reported inaccessible
responses for a guide index and an unconfirmed containers path; these are
discovery failures, not a claim that the publisher blocks those pages. All six
selected direct HTTP acquisitions succeeded. No login, token, model download,
container pull or device command was attempted.

Conflicting scope is retained: the hardware page's fixed 128 GB description
coexists with release-note/software support for 64 GB units; the two hardware
descriptions disagree on Bluetooth version; the dependency table's internal
date precedes its footer. Broad shared-memory prose does not override the CUDA
page's narrower coherent-access/RDMA restriction. Resolve installed details
through exact SKU and capability checks rather than selecting convenient claims.

The [analysis](../../../../docs/gb10-deployment-evidence.md) separates reported
facts from HMS design inferences. The source examples were read as proposed
workflows, not run. Their suggested models, image tags and shell commands are
not a recommended or qualified HMS deployment. Known issues, ARM memory-ordering
details, complete container/dependency closures, model licenses and multi-node
protocol behavior are further work. Actual firmware/driver/kernel identity,
ARM64 builds, loaded-memory behavior, scheduling tails, thermal response,
peripheral access and independent endpoint protection remain unmeasured.
