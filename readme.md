##PostCommitHookMixin

Creates a hook that signals the transaction has been committed to the database.  This is more reliable than the
builtin save method or Django's post_save signals, which are called before commit within atomic transactions.

To use:
    * Add the mixin to the model
    * Add the following 'field' to the model:
        tracker = FieldTracker()
            * This is not actually a field in the database, but a third-party package used for tracking state
            changes.
            * Also specify a subset of fields to be tracked, BUT 'id' must always be tracked in order to signal
            initial creation.
            * See documentation: http://django-model-utils.readthedocs.io/en/latest/utilities.html#field-tracker
    * Implement the post_commit_hook method.
