"""The two streaming paths and the helpers they share.

`langchain_path` is the default; `direct_client` takes over when the turn
needs OpenRouter response fields LangChain does not surface (reasoning
details, generated images). Each is a mixin so that its `return`
statements keep terminating the whole stream -- turning a yielding block
into a sub-generator would silently change that.

The helper modules here hold only NON-yielding work lifted out of those
generators.
"""
