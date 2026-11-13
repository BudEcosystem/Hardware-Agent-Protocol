### verifyDepsBeforeRun

* Default: **false**
* Type: **install**, **warn**, **error**, **prompt**, **false**

This setting allows the checking of the state of dependencies before running scripts. The check runs on `pnpm run` and `pnpm exec` commands. The following values are supported:

- `install` - Automatically runs install if `node_modules` is not up to date.
- `warn` - Prints a warning if `node_modules` is not up to date.
- `prompt` - Prompts the user for permission to run install if `node_modules` is not up to date.
- `error` - Throws an error if `node_modules` is not up to date.
- `false` - Disables dependency checks.

