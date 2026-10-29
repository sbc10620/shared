# Design principles

Read by the implementer (dev-cycle steps 4 and 8) and given to both
reviewers (steps 2 and 6), besides correctness. The list is
language-neutral: it holds for object-oriented, functional and
multi-paradigm code alike. Read "module" as whatever unit the language
groups code by (class, module, package, crate, file), and "interface" as
whatever it abstracts behaviour with (interface, trait, protocol, abstract
class, function type, closure).

Scope: judge only what the change adds or changes, plus existing structure
the change extends (a new entry in an existing global table extends that
table). A principle the untouched code already breaks is out of scope.

Each item: what to look for, then the usual fix. A reviewer prompt carries
each item as one line: the principle's name and its "Look for" cell.

**SOLID**

| Principle | Look for | Usual fix |
| --- | --- | --- |
| Single responsibility | One module or function that changes for two unrelated reasons (parsing and policy, scanning and reporting) | Split along the reason to change |
| Open/closed | Adding a case (a country, a provider, a rule) means editing a central list or `switch` in code that is otherwise generic | Let the case register itself, or pass the cases in; an exhaustive `match` the compiler checks is acceptable when it is the ONE mapping place |
| Liskov substitution | An implementation of an interface that rejects inputs, panics or ignores calls the interface allows; a caller that checks which implementation it got | Make the implementation honour the contract, or narrow the interface |
| Interface segregation | A caller forced to provide or depend on members it never uses (dummy closures, `unimplemented!()`, no-op callbacks) | Split the interface |
| Dependency inversion | A generic, lower-level component (an engine, a store, a transport) that names a specific consumer's concept (a domain type, a product rule, a data format only one caller uses) | The generic component depends on an abstraction (an interface, a function parameter); the consumer supplies the concrete behaviour |

**Dependencies and state**

| Principle | Look for | Usual fix |
| --- | --- | --- |
| Explicit dependencies (dependency injection) | Code that reaches a process-wide registry, global table, singleton or environment variable to find what it needs, where the caller already knows it | Pass it in: an argument, a constructor field, a closure that captures it |
| Least privilege / least knowledge | A component that can see more than its job needs (every country's table when two are selected; a whole config when it reads one key); a chain of reaches through other objects' internals | Hand it only the subset it uses |
| Mechanism vs policy | A reusable mechanism with a hard-coded decision that belongs to one user of it | Keep the mechanism generic; take the decision as a parameter or hook |
| No boolean flag parameters | A `bool` (or mode enum) that makes the callee branch on the caller's situation | Pass the behaviour itself (a function, a strategy value), or split into two functions |
| Global mutable state | New process-wide mutable state, or new readers of it | Prefer values passed down; if it must exist, one owner, set once, documented |

**Make mistakes impossible, or loud**

| Principle | Look for | Usual fix |
| --- | --- | --- |
| Illegal states unrepresentable | An invariant kept only by a naming convention, a comment or a test (unique names across tables, "always set together") | Encode it in types or construction: a constructor that refuses duplicates, a required field, an exhaustive `match` |
| Fail fast | A misconfiguration that is logged and skipped, or silently resolved to a default, where a build or boot error would be safe | Refuse at build or boot time; keep fail-open only where a documented decision says so |
| Explicit over implicit | Behaviour inferred from something incidental (a name prefix, list order, the first match in a search) when an explicit value is available | Use the explicit value; if inference stays, test the rule it relies on |
| Consistency / least astonishment | A module laid out, named or wired differently from its siblings without a reason | Match the siblings, or state the reason in a comment |

## Reporting a design finding

A design finding names the principle and the concrete code (`file:line`),
and says what the fix would change for a caller. Without a runtime effect
it is labelled "사실이지만 동작 영향 없음", with "설계:" leading its 지적
cell, so the user can pick it out; with a runtime effect (a wrong lookup, a
skipped guard) it is "고칠 결함" like any other defect. Do not report a
principle in the abstract, nor one the user already decided against (it
goes in the "do not re-argue" list).
