import threading

from expiringdict import ExpiringDict

from django.db import models, transaction


# using the ExpiringDict allows us to flush keys from transactions that were never committed to the database
# TODO: set values as constants and pull from settings file
model_tracker_cache = ExpiringDict(max_len=5000, max_age_seconds=30)


class PostCommitHookMixin(models.Model):
    """
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
    """

    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not hasattr(self, 'tracker'):
            raise NotImplementedError('PostCommitHookMixin implementation error: "tracker" is a required field but is '
                                      'missing from the model {}.'.format(self.__class__.__name__))
        if 'id' not in self.tracker.fields:
            raise NotImplementedError('PostCommitHookMixin implementation error: "id" must be in the list of tracked '
                                      'fields but is missing from the {} model.'.format(self.__class__.__name__))

    def save(self, **kwargs):
        obj = super().save(**kwargs)
        fields_changed_dict = self.tracker.changed()

        # not sending post_commit signal if fields are not changed
        date_updated_only = (len(fields_changed_dict) == 1) and ('date_updated' in fields_changed_dict)
        no_changes = not fields_changed_dict or date_updated_only
        if no_changes:
            return obj

        connection = transaction.get_connection()
        if connection.in_atomic_block:
            if model_tracker_cache.get(self.cache_key):
                # Maintain the oldest values, and adds any new ones.
                fields_changed_dict.update(model_tracker_cache[self.cache_key])
                model_tracker_cache[self.cache_key] = fields_changed_dict
            else:
                model_tracker_cache[self.cache_key] = fields_changed_dict

            transaction.on_commit(self.post_atomic_commit_handler)

        else:
            created = 'id' in fields_changed_dict
            self.post_commit_hook(fields_changed_dict.keys(), created, fields_changed_dict)

        return obj

    def post_atomic_commit_handler(self):
        """
        Lookup any changes made to the instance in the model_tracker_cache and pass them to the post_commit_hook.

        This method can be called multiple times in an atomic transaction.  For example, if an instance is created
        then modified in the same transaction, this will be executed twice.  But it is designed to only call
        self.post_commit_hook once, on the first execution.
        """
        fields_changed_dict = model_tracker_cache.get(self.cache_key)
        if fields_changed_dict:
            created = 'id' in fields_changed_dict
            self.post_commit_hook(fields_changed_dict.keys(), created, fields_changed_dict)
            # remove key from dict to prevent duplicate calls
            model_tracker_cache.pop(self.cache_key)

    @property
    def cache_key(self):
        transaction_id = threading.get_ident()
        return '{}-{}-{}'.format(self.__class__.__name__, self.id, transaction_id)

    def post_commit_hook(self, fields_changed, created, original_values_dict):
        raise NotImplementedError('PostCommitHookMixin implementation error: {} must implement the post_commit_hook '
                                  'method.'.format(self.__class__.__name__))
