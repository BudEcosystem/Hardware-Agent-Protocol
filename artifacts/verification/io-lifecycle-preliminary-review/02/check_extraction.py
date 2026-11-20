"""AST comparison only; reads source without importing or executing project code."""
import ast
import copy
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent

def method(path, class_name, name):
    tree=ast.parse(path.read_text())
    cls=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name==class_name)
    return next(node for node in cls.body if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name==name)
def body_dump(nodes):
    return ast.dump(ast.Module(body=nodes,type_ignores=[]),include_attributes=False)
class Deployment(ast.NodeTransformer):
    def visit_Attribute(self,node):
        if isinstance(node.value,ast.Name) and node.value.id=='owner' and node.attr=='deployment':
            return ast.Name(id='deployment',ctx=ast.Load())
        return self.generic_visit(node)
old=method(HERE/'baseline/hms/registry.py','Registry','_bind_in_tx')
new=method(HERE/'source/hms/registry.py','Registry','_bind_checked_in_tx')
public=method(HERE/'source/hms/registry.py','Registry','_bind_in_tx')
old_tail=copy.deepcopy(old.body[3:])
old_tail=[Deployment().visit(node) for node in old_tail]
old_release=method(HERE/'baseline/hms/journal.py','Journal','release_resources')
new_release=method(HERE/'source/hms/journal.py','Journal','_release_resources_in_tx')
checks={
 'registryPublicAuthorizationPrefixPreserved':body_dump(old.body[:3])==body_dump(public.body[:3]),
 'registryBindingTailPreservedAfterExplicitTxGuardAndDeploymentRename':body_dump(old_tail)==body_dump(new.body[2:]),
 'journalOriginalReleaseBodyPreservedAfterExplicitTxGuard':body_dump(old_release.body[0].body)==body_dump(new_release.body[1:]),
 'registryHelperStartsWithDocstringThenGuard':isinstance(new.body[0],ast.Expr) and isinstance(new.body[1],ast.If),
 'journalHelperStartsWithGuard':isinstance(new_release.body[0],ast.If),
 'projectImports':False,'projectExecution':False}
assert all(value for key,value in checks.items() if key not in {'projectImports','projectExecution'})
(HERE/'extraction-result.json').write_text(json.dumps(checks,indent=2)+'\n')
print(json.dumps(checks,indent=2))
