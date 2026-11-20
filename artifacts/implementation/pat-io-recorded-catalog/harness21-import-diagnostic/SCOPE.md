# Import-only diagnosis

Reproduce module loading under the original frozen source and process guard, retain unittest loader errors, then stop before every test method. No database or worker may start. The expected wrapper outcome is failure because this is not a test execution scope.
