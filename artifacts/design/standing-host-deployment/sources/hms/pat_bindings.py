"""Trusted installed metadata joined to current registry bindings for PAT reuse.

The registration carries explicit units/frames and declared driver identity; it
does not attest a driver binary or commission hardware. Discovery reads only the
shared authority database. It never refreshes a device, examines resource
contention, or treats cached presence as evidence of current availability.
"""
import copy
import hashlib
import itertools
import json
import re

from .contracts import ContractError, canonical, identifier
from .installations import installation_digest
from .journal import JournalError
from .pat_compiler import _binding
from .pat_contracts import parse_pat, snapshot


MAX_ASSIGNMENTS = 16
_FIELDS = {"instanceId", "typeDigest", "driverProfile", "driverDigest",
           "installationDigest", "argumentMetadata"}


class RegistryPatBindings:
    """Complete bounded enumeration from immutable, explicitly installed data.

    Construct from trusted application setup, never caller JSON. Call inside
    the owning Journal transaction. Missing metadata or a session for an
    otherwise compatible authorized installed candidate is indeterminate,
    not no-match. Raw registry entries outside the installed adapter maps are
    not executable candidates. These maps currently have at most 16 routes.
    Endpoint sessions may come from expired presence rows; child admission and
    dispatch separately enforce actual freshness and session continuity.
    """
    def __init__(self, runtime, registrations):
        if type(registrations) not in {list, tuple} or not 1 <= len(registrations) <= 128:
            raise ContractError("PAT binding registrations require 1..128 entries")
        values = snapshot(list(registrations), "PAT_INVALID_BINDING_REGISTRATION")
        seen = set()
        for value in values:
            if type(value) is not dict or set(value) != _FIELDS:
                raise ContractError("invalid PAT binding registration fields")
            identifier(value["instanceId"])
            identifier(value["driverProfile"])
            if value["instanceId"] in seen:
                raise ContractError("duplicate PAT binding registration")
            seen.add(value["instanceId"])
            for field in ("typeDigest", "driverDigest", "installationDigest"):
                if type(value[field]) is not str or re.fullmatch(r"sha256:[0-9a-f]{64}", value[field]) is None:
                    raise ContractError("invalid PAT binding registration digest")
            metadata = value["argumentMetadata"]
            if type(metadata) is not dict or not 1 <= len(metadata) <= 32 or len(canonical(metadata)) > 16384:
                raise ContractError("invalid PAT argument metadata registration")
            for action in metadata:
                identifier(action)
        self.journal = runtime.journal
        self.registry = runtime.registry
        if self.registry.journal is not self.journal:
            raise JournalError("PAT_AUTHORITY_MISMATCH")
        self._registrations = tuple(sorted(values, key=lambda value: value["instanceId"]))
        self.registration_identity = "sha256:" + hashlib.sha256(
            b"HMS-PAT-BINDING-REGISTRATIONS-v0.1\0" + canonical(list(self._registrations))).hexdigest()

    def _check_context(self, context):
        if not self.journal._db.in_transaction:
            raise JournalError("PAT_BINDING_TRANSACTION_REQUIRED")
        if context.deployment != self.registry.deployment:
            raise JournalError("ACCESS_DENIED")

    def _candidate(self, context, requirement, registration):
        reg = self.registry
        instance_id = registration["instanceId"]
        instance = reg._instance(instance_id)
        binding, active = reg._binding(instance_id)
        if instance["retired"] or not active or instance["deployment"] != context.deployment:
            return None
        bundle = reg._type(instance["type_digest"])
        actions = requirement["actions"]
        if (requirement["capabilityFamily"] not in bundle["execution"]["capabilities"] or
                not set(actions) <= set(bundle["execution"]["actions"])):
            return None
        if not reg.allowed(context, "read", instance_id) or any(
                not reg.allowed(context, "invoke:" + action, instance_id) for action in actions):
            return None
        installed = reg._db.execute("SELECT * FROM rt_adapters WHERE adapter=?", (binding["adapterId"],)).fetchone()
        if installed is None or not installed["ready"]:
            raise JournalError("PAT_BINDING_INSTALLATION_UNAVAILABLE")
        installation = json.loads(installed["document"])
        digest = installation_digest(installation)
        if installation["driver"] not in requirement["driverProfiles"]:
            return None
        if (installed["digest"] != digest or canonical(installation) != bytes(installed["document"]) or
                "sha256:" + digest != registration["installationDigest"] or
                installation["driver"] != registration["driverProfile"] or
                instance_id not in installation["instances"].values() or
                instance["type_digest"] != registration["typeDigest"] or
                binding["typeDigest"] != registration["typeDigest"]):
            raise JournalError("PAT_BINDING_REGISTRATION_CHANGED")
        metadata = registration["argumentMetadata"]
        if not set(actions) <= set(metadata):
            raise JournalError("PAT_BINDING_METADATA_MISSING")
        presence = reg._db.execute("SELECT session FROM reg_presence WHERE instance=?", (instance_id,)).fetchone()
        if presence is None:
            raise JournalError("PAT_BINDING_SESSION_UNKNOWN")
        descriptor = {"type": copy.deepcopy(bundle), "binding": copy.deepcopy(binding),
            "endpointSession": presence["session"], "driverProfile": registration["driverProfile"],
            "driverDigest": registration["driverDigest"], "installationDigest": registration["installationDigest"],
            "argumentMetadata": {action: copy.deepcopy(metadata[action]) for action in actions}}
        _binding(descriptor, requirement)
        return descriptor

    def _check_registration_coverage(self, context, requirement):
        """Do not turn an installed candidate's missing metadata into uniqueness."""
        registered = {row["instanceId"] for row in self._registrations}
        routes = self.registry._db.execute("SELECT * FROM rt_adapters ORDER BY adapter LIMIT 17").fetchall()
        if len(routes) > 16:
            raise JournalError("PAT_BINDING_ENUMERATION_LIMIT")
        for row in routes:
            installation = json.loads(row["document"])
            digest = installation_digest(installation)
            if row["digest"] != digest:
                raise JournalError("PAT_BINDING_REGISTRATION_CHANGED")
            if (canonical(installation) != bytes(row["document"]) or
                    installation["adapterId"] != row["adapter"]):
                raise JournalError("PAT_BINDING_REGISTRATION_CHANGED")
            if installation["driver"] not in requirement["driverProfiles"]:
                continue
            for instance_id in installation["instances"].values():
                instance = self.registry._instance(instance_id)
                binding, active = self.registry._binding(instance_id)
                if (instance["retired"] or not active or instance["deployment"] != context.deployment or
                        binding["adapterId"] != row["adapter"]):
                    continue
                bundle = self.registry._type(instance["type_digest"])
                actions = requirement["actions"]
                if (requirement["capabilityFamily"] not in bundle["execution"]["capabilities"] or
                        not set(actions) <= set(bundle["execution"]["actions"]) or
                        not self.registry.allowed(context, "read", instance_id) or
                        any(not self.registry.allowed(context, "invoke:" + action, instance_id) for action in actions)):
                    continue
                if not row["ready"]:
                    raise JournalError("PAT_BINDING_INSTALLATION_UNAVAILABLE")
                if instance_id not in registered:
                    raise JournalError("PAT_BINDING_METADATA_MISSING")

    def __call__(self, context, artifact, request):
        # The request is intentionally not used to install descriptors or narrow
        # the device inventory. Typed parameters are bound by the PAT compiler.
        self._check_context(context)
        program = parse_pat(artifact)
        choices = []
        roles = sorted(program["roles"])
        for role in roles:
            self._check_registration_coverage(context, program["roles"][role])
            candidates = []
            for registration in self._registrations:
                candidate = self._candidate(context, program["roles"][role], registration)
                if candidate is not None:
                    candidates.append(candidate)
            choices.append(candidates)
        total = 1
        for candidates in choices:
            total *= len(candidates)
        if total > MAX_ASSIGNMENTS:
            raise JournalError("PAT_BINDING_ENUMERATION_LIMIT")
        return {"complete": True, "assignments": [
            {role: copy.deepcopy(descriptor) for role, descriptor in zip(roles, assignment)}
            for assignment in itertools.product(*choices)]}

    def for_roles(self, context, artifact, role_instances):
        """Explicit trusted qualification assignment, never a run-request field.

        This helper lets an installed evaluator/environment provider select its
        declared test deployment. Run selection must use complete enumeration.
        """
        self._check_context(context)
        program = parse_pat(artifact)
        if type(role_instances) is not dict or set(role_instances) != set(program["roles"]):
            raise ContractError("invalid PAT qualification role assignment")
        records = {value["instanceId"]: value for value in self._registrations}
        result = {}
        for role, instance in role_instances.items():
            identifier(instance)
            if instance not in records:
                raise JournalError("PAT_BINDING_NOT_REGISTERED")
            descriptor = self._candidate(context, program["roles"][role], records[instance])
            if descriptor is None:
                raise JournalError("PAT_BINDING_NOT_APPLICABLE")
            result[role] = descriptor
        return result
