'''
Created on 14 janv. 2015

@author: Remi Cattiau
'''
from nxdrive.engine.engine import Worker
from nxdrive.logging_config import get_logger
from nxdrive.client.common import LOCALLY_EDITED_FOLDER_NAME
import os
log = get_logger(__name__)

WindowsError = None
try:
    from exceptions import WindowsError
except ImportError:
    pass  # this will never be raised under unix


class Processor(Worker):
    '''
    classdocs
    '''

    def __init__(self, engine, item_getter, name=None):
        '''
        Constructor
        '''
        super(Processor, self).__init__(engine, name=name)
        self._current_item = None
        self._get_item = item_getter
        self._engine = engine
        self._dao = self._engine.get_dao()

    def _clean(self, reason):
        if reason == 'exception':
            # Add it back to the queue ? Add the error delay
            self.republish()

    def republish(self, doc_pair=None):
            from time import sleep
            sleep(10)
            if doc_pair is None:
                doc_pair = self._current_item
            if doc_pair is not None:
                self._engine.get_queue_manager().push(doc_pair)

    def acquire_state(self, row_id):
        if self._dao.acquire_processor(self._thread_id, row_id):
            return self._dao.get_state_from_id(row_id)
        return None

    def release_state(self):
        self._dao.release_processor(self._thread_id)

    def _execute(self):
        self._current_item = self._get_item()
        local_client = self._engine.get_local_client()
        remote_client = self._engine.get_remote_client()
        while (self._current_item != None):
            doc_pair = self.acquire_state(self._current_item.id)
            try:
                if (doc_pair is None or
                    doc_pair.pair_state == 'synchronized'
                    or doc_pair.pair_state == 'unsynchronized'):
                    log.trace("Skip as pair is None or in non-processable state: %r", doc_pair)
                    self._current_item = self._get_item()
                    continue
                parent_path = doc_pair.local_parent_path
                if (parent_path == ''):
                    parent_path = "/"
                if not local_client.exists(parent_path):
                    log.trace("Republish as parent doesn't exist : %r", doc_pair)
                    self.republish(doc_pair)
                    continue
                handler_name = '_synchronize_' + doc_pair.pair_state
                sync_handler = getattr(self, handler_name, None)
                if sync_handler is None:
                    raise RuntimeError("Unhandled pair_state: %r for %r",
                                       doc_pair.pair_state, doc_pair)
                else:
                    log.trace("Calling %s on doc pair %r", sync_handler, doc_pair)
                    sync_handler(doc_pair, local_client, remote_client)
                    log.trace("Finish %s on doc pair %r", sync_handler, doc_pair)
            finally:
                self.release_state()
            self._interact()
            self._current_item = self._get_item()

    def _synchronize_conflicted(self, doc_pair, local_client, remote_client):
        # Auto-resolve conflict
        if not doc_pair.folderish:
            if doc_pair.remote_digest == doc_pair.local_digest:
                log.debug("Auto-resolve conflict has digest are the same")
                self._dao.synchronize_state(doc_pair)

    def _synchronize_locally_modified(self, doc_pair, local_client, remote_client):
        if doc_pair.remote_digest != doc_pair.local_digest:
            if doc_pair.remote_can_update:
                log.debug("Updating remote document '%s'.",
                          doc_pair.remote_name)
                remote_client.stream_update(
                    doc_pair.remote_ref,
                    local_client._abspath(doc_pair.local_path),
                    parent_fs_item_id=doc_pair.remote_parent_ref,
                    filename=doc_pair.remote_name,
                )
                self._refresh_remote(doc_pair, remote_client)
                # TODO refresh_client
            else:
                log.debug("Skip update of remote document '%s'"\
                             " as it is readonly.",
                          doc_pair.remote_name)
                if self._controller.local_rollback():
                    local_client.delete(doc_pair.local_path)
                    self._dao.mark_descendants_remotely_created(doc_pair)
                else:
                    self._dao.synchronize_state(doc_pair, state='unsynchronized')
                return
        self._dao.synchronize_state(doc_pair)

    def _get_normal_state_from_remote_ref(self, ref):
        # TODO Select the only states that is not a collection
        return self._dao.get_states_from_remote(ref)[0]

    def _synchronize_locally_created(self, doc_pair, local_client, remote_client):
        name = os.path.basename(doc_pair.local_path)
        # Find the parent pair to find the ref of the remote folder to
        # create the document
        parent_pair = self._dao.get_state_from_local(doc_pair.local_parent_path)
        if parent_pair is None:
            # Try to get it from xattr
            log.trace("Fallback to xattr")
            if local_client.exists(doc_pair.local_parent_path):
                parent_ref = local_client.get_remote_id(doc_pair.local_parent_path)
                parent_pair = self._get_normal_state_from_remote_ref(parent_ref)
        if parent_pair is None or parent_pair.remote_ref is None:
            # Illegal state: report the error and let's wait for the
            # parent folder issue to get resolved first
            raise ValueError(
                "Parent folder of %s is not bound to a remote folder"
                % doc_pair.local_parent_path)
        parent_ref = parent_pair.remote_ref
        if parent_pair.remote_can_create_child:
            remote_parent_path = parent_pair.remote_parent_path + '/' + parent_pair.remote_ref
            if doc_pair.folderish:
                log.debug("Creating remote folder '%s' in folder '%s'",
                          name, parent_pair.remote_name)
                remote_ref = remote_client.make_folder(parent_ref, name)
            else:
                # TODO Check if the file is already on the server with the good digest
                log.debug("Creating remote document '%s' in folder '%s'",
                          name, parent_pair.remote_name)
                remote_ref = remote_client.stream_file(
                    parent_ref, local_client._abspath(doc_pair.local_path), filename=name)
            self._dao.update_remote_state(doc_pair, remote_client.get_info(remote_ref), remote_parent_path)
            local_client.set_remote_id(doc_pair.local_path, remote_ref)
            self._dao.synchronize_state(doc_pair, doc_pair.version + 1)
        else:
            child_type = 'folder' if doc_pair.folderish else 'file'
            log.warning("Won't synchronize %s '%s' created in"
                        " local folder '%s' since it is readonly",
                child_type, doc_pair.local_name, parent_pair.local_name)
            if doc_pair.folderish:
                doc_pair.remote_can_create_child = False
            if self._engine.local_rollback():
                local_client.delete(doc_pair.local_path)
                self._dao.remove_pair(doc_pair)
            else:
                self._dao.synchronize_state(doc_pair, state='unsynchronized')

    def _synchronize_locally_deleted(self, doc_pair, local_client, remote_client):
        if doc_pair.remote_ref is not None:
            if doc_pair.remote_can_delete:
                log.debug("Deleting or unregistering remote document"
                          " '%s' (%s)",
                          doc_pair.remote_name, doc_pair.remote_ref)
                if doc_pair.remote_state != 'deleted':
                    remote_client.delete(doc_pair.remote_ref,
                                parent_fs_item_id=doc_pair.remote_parent_ref)
                self._dao.remove_pair(doc_pair)
            else:
                log.debug("Marking %s as remotely created since remote"
                          " document '%s' (%s) can not be deleted: either"
                          " it is readonly or it is a virtual folder that"
                          " doesn't exist in the server hierarchy",
                          doc_pair, doc_pair.remote_name, doc_pair.remote_ref)
                if doc_pair.remote_state != 'deleted':
                    self._dao.mark_descendants_remotely_created(doc_pair)


    def _synchronize_locally_moved_created(self, doc_pair, local_client, remote_client):
        doc_pair.remote_ref = None
        self._synchronize_locally_created(doc_pair, local_client, remote_client)

    def _synchronize_locally_moved(self, doc_pair, local_client, remote_client):
        # A file has been moved locally, and an error occurs when tried to
        # move on the server
        if doc_pair.local_name != doc_pair.remote_name:
            try:
                log.debug('Renaming remote file according to local : %r',
                                                    doc_pair)
                remote_info = remote_client.rename(doc_pair.remote_ref,
                                                        doc_pair.local_name)
                self._refresh_remote(doc_pair, remote_client, remote_info=remote_info)
                doc_pair.version = doc_pair.version + 1
            except Exception as e:
                log.debug(e)
                self._handle_failed_remote_rename(doc_pair, doc_pair)
                return
        parent_pair = self._dao.get_state_from_local(doc_pair.local_parent_path)
        if (parent_pair is not None
            and parent_pair.remote_ref != doc_pair.remote_parent_ref):
            log.debug('Moving remote file according to local : %r', doc_pair)
            # Bug if move in a parent with no rights / partial move
            # if rename at the same time
            parent_path = parent_pair.remote_path + "/" + parent_pair.remote_ref
            remote_info = remote_client.move(doc_pair.remote_ref,
                        parent_pair.remote_ref)
            self._dao.update_remote_state(doc_pair, remote_info, parent_path)
            doc_pair.version = doc_pair.version + 1
        self._dao.synchronize_state(doc_pair)

    def _synchronize_deleted_unknown(self, doc_pair, local_client, remote_client):
        # Somehow a pair can get to an inconsistent state:
        # <local_state=u'deleted', remote_state=u'unknown',
        # pair_state=u'unknown'>
        # Even though we are not able to figure out how this can happen we
        # need to handle this case to put the database back to a consistent
        # state.
        # This is tracked by https://jira.nuxeo.com/browse/NXP-14039
        log.debug("Inconsistency should not happens anymore")
        log.debug("Detected inconsistent doc pair %r, deleting it hoping the"
                  " synchronizer will fix this case at next iteration",
                  doc_pair)
        self._dao.remove_state(doc_pair)

    def _download_content(self, local_client, remote_client, doc_pair, file_path):
        # Check if the file is already on the HD
        pair = self._dao.get_valid_duplicate_file(doc_pair.remote_digest)
        if pair:
            import shutil
            from nxdrive.client.base_automation_client import DOWNLOAD_TMP_FILE_PREFIX
            from nxdrive.client.base_automation_client import DOWNLOAD_TMP_FILE_SUFFIX
            file_dir = os.path.dirname(file_path)
            file_name = os.path.basename(file_path)
            file_out = os.path.join(file_dir, DOWNLOAD_TMP_FILE_PREFIX + file_name
                                + DOWNLOAD_TMP_FILE_SUFFIX)
            shutil.copy(local_client._abspath(pair.local_path), file_out)
            return file_out
        tmp_file = remote_client.stream_content(
                                doc_pair.remote_ref, file_path,
                                parent_fs_item_id=doc_pair.remote_parent_ref)
        return tmp_file

    def _synchronize_remotely_modified(self, doc_pair, local_client, remote_client):
        try:
            is_renaming = doc_pair.remote_name != doc_pair.local_name
            if doc_pair.remote_digest != doc_pair.local_digest != None:
                os_path = local_client._abspath(doc_pair.local_path)
                if is_renaming:
                    new_os_path = os.path.join(os.path.dirname(os_path),
                                               doc_pair.remote_name)
                    log.debug("Replacing local file '%s' by '%s'.",
                              os_path, new_os_path)
                else:
                    new_os_path = os_path
                    log.debug("Updating content of local file '%s'.",
                              os_path)
                tmp_file = self._download_content(local_client, remote_client, doc_pair, new_os_path)
                # Delete original file and rename tmp file
                local_client.delete(doc_pair.local_path)
                updated_info = local_client.rename(
                                            local_client.get_path(tmp_file),
                                            doc_pair.remote_name)
                self._refresh_local_state(doc_pair, updated_info)
            else:
                # digest agree so this might be a renaming and/or a move,
                # and no need to transfer additional bytes over the network
                is_move, new_parent_pair = self._is_remote_move(doc_pair)
                if remote_client.is_filtered(doc_pair.remote_parent_path):
                    # A move to a filtered parent ( treat it as deletion )
                    self._synchronize_remotely_deleted(doc_pair, local_client, remote_client)
                    return
                if not is_move and not is_renaming:
                    log.debug("No local impact of metadata update on"
                              " document '%s'.", doc_pair.remote_name)
                else:
                    file_or_folder = 'folder' if doc_pair.folderish else 'file'
                    previous_local_path = doc_pair.local_path
                    if is_move:
                        # move
                        log.debug("Moving local %s '%s' to '%s'.",
                            file_or_folder, local_client._abspath(doc_pair.local_path),
                            local_client._abspath(new_parent_pair.local_path))
                        # May need to add a lock for move
                        updated_info = local_client.move(doc_pair.local_path,
                                          new_parent_pair.local_path)
                        new_parent_path = new_parent_pair.remote_parent_path + "/" + new_parent_pair.remote_ref
                        self._dao.update_remote_parent_path(doc_pair, new_parent_path)
                        # refresh doc pair for the case of a
                        # simultaneous move and renaming
                        previous_local_path = updated_info.path
                    if is_renaming:
                        # renaming
                        log.debug("Renaming local %s '%s' to '%s'.",
                            file_or_folder, local_client._abspath(previous_local_path),
                            doc_pair.remote_name)
                        updated_info = local_client.rename(
                            doc_pair.local_path, doc_pair.remote_name)
                    if is_move or is_renaming:
                        # Should call a DAO method
                        self._dao.update_local_parent_path(doc_pair, os.path.basename(updated_info.path),
                                                           os.path.dirname(updated_info.path))
                        self._refresh_local_state(doc_pair, updated_info)
                        #self._local_rename_with_descendant_states(doc_pair, previous_local_path, updated_info.path)
            self._handle_readonly(local_client, doc_pair)
            self._dao.synchronize_state(doc_pair)
        except (IOError, WindowsError) as e:
            log.warning(
                "Delaying local update of remotely modified content %r due to"
                " concurrent file access (probably opened by another"
                " process).",
                doc_pair)
            raise e

    def _synchronize_remotely_created(self, doc_pair, local_client, remote_client):
        name = doc_pair.remote_name
        # Find the parent pair to find the path of the local folder to
        # create the document into
        parent_pair = self._dao.get_states_from_remote(doc_pair.remote_parent_ref)[0]
        if parent_pair is None:
            # Illegal state: report the error and let's wait for the
            # parent folder issue to get resolved first
            raise ValueError(
                "Could not find parent folder of doc %r (%r)"
                " folder" % (name, doc_pair.remote_ref))
        if parent_pair.local_path is None:
            # Illegal state: report the error and let's wait for the
            # parent folder issue to get resolved first
            raise ValueError(
                "Parent folder of doc %r (%r) is not bound to a local"
                " folder" % (name, doc_pair.remote_ref))
        path = doc_pair.remote_parent_path + '/' + doc_pair.remote_ref
        if remote_client.is_filtered(path):
            # It is filtered so skip and remove from the LastKnownState
            self._dao.remove_state(doc_pair)
            return
        local_parent_path = parent_pair.local_path
        if doc_pair.folderish:
            log.debug("Creating local folder '%s' in '%s'", name,
                      local_client._abspath(parent_pair.local_path))
            path = local_client.make_folder(local_parent_path, name)
        else:
            path, os_path, name = local_client.get_new_file(local_parent_path,
                                                            name)
            log.debug("Creating local file '%s' in '%s'", name,
                      local_client._abspath(parent_pair.local_path))
            tmp_file = self._download_content(local_client, remote_client, doc_pair, os_path)
            # Rename tmp file
            local_client.rename(local_client.get_path(tmp_file), name)
        local_client.set_remote_id(path, doc_pair.remote_ref)
        self._handle_readonly(local_client, doc_pair)
        self._refresh_local_state(doc_pair, local_client.get_info(path))
        if not self._dao.synchronize_state(doc_pair, doc_pair.version):
            log.debug("Pair is not in synchronized state (version issue): %r", doc_pair)

    def _synchronize_remotely_deleted(self, doc_pair, local_client, remote_client):
        try:
            if doc_pair.local_state != 'deleted':
                if self._engine.use_trash():
                    local_client.delete(doc_pair.local_path)
                else:
                    local_client.delete_final(doc_pair.local_path)
            self._dao.remove_pair(doc_pair)
        except (IOError, WindowsError) as e:
            # Under Windows deletion can be impossible while another
            # process is accessing the same file (e.g. word processor)
            # TODO: be more specific as detecting this case:
            # shall we restrict to the case e.errno == 13 ?
            log.warning(
                "Delaying local deletion of remotely deleted item %r due to"
                " concurrent file access (probably opened by another"
                " process).", doc_pair)
            raise e

    def _synchronize_unknown_deleted(self, doc_pair, local_client, remote_client):
        # Somehow a pair can get to an inconsistent state:
        # <local_state=u'unknown', remote_state=u'deleted',
        # pair_state=u'unknown'>
        # Even though we are not able to figure out how this can happen we
        # need to handle this case to put the database back to a consistent
        # state.
        # This is tracked by https://jira.nuxeo.com/browse/NXP-13216
        log.debug("Inconsistency should not happens anymore")
        log.debug("Detected inconsistent doc pair %r, deleting it hoping the"
                  " synchronizer will fix this case at next iteration",
                  doc_pair)
        self._dao.remove_state(doc_pair)
        if doc_pair.local_path is not None:
            log.debug("Since the local path is not None: %s, the synchronizer"
                      " will probably consider this as a local creation at"
                      " next iteration and create the file or folder remotely",
                      doc_pair.local_path)
        else:
            log.debug("Since the local path is None the synchronizer will"
                      " probably do nothing at next iteration")

    def _refresh_remote(self, doc_pair, remote_client, remote_info=None):
        if remote_info is None:
            remote_info = None # Get from remote_client
            remote_info = remote_client.get_info(doc_pair.remote_ref)
        self._dao.update_remote_state(doc_pair, remote_info, versionned=False)

    def _refresh_local_state(self, doc_pair, local_info):
        if doc_pair.local_digest is None and not doc_pair.folderish:
            doc_pair.local_digest = local_info.get_digest()
        self._dao.update_local_state(doc_pair, local_info, versionned=False)
        doc_pair.local_path = local_info.path
        doc_pair.local_name = os.path.basename(local_info.path)
        doc_pair.last_local_updated = local_info.last_modification_time

    def _is_remote_move(self, doc_pair):
        local_parent_pair = self._dao.get_state_from_local(doc_pair.local_parent_path)
        remote_parent_pair = self._dao.get_states_from_remote(doc_pair.remote_parent_ref)[0]
        return (local_parent_pair is not None
                and remote_parent_pair is not None
                and local_parent_pair.id != remote_parent_pair.id,
                remote_parent_pair)

    def _handle_failed_remote_rename(self, source_pair, target_pair):
        # An error occurs return false
        log.error("Renaming from %s to %s canceled",
                            target_pair.remote_name, target_pair.local_name)
        if self._engine.local_rollback():
            try:
                local_client = self._engine.get_local_client()
                info = local_client.rename(target_pair.local_path,
                                            target_pair.remote_name)
                self._dao.update_local_state(source_pair, info)
                if source_pair != target_pair:
                    if target_pair.folderish:
                        # Remove "new" created tree
                        pairs = self._dao.get_states_from_partial_local(
                                target_pair.local_path).all()
                        for pair in pairs:
                            self._dao.remove_state(pair)
                        pairs = self._dao.get_states_from_partial_local(
                                source_pair.local_path).all()
                        for pair in pairs:
                            self._dao.synchronize_state(pair)
                    else:
                        self._dao.remove_state(target_pair)
                    # Mark all local as unknown
                    #self._mark_unknown_local_recursive(session, source_pair)
                self._dao.synchronize_state(source_pair)
                return True
            except Exception, e:
                log.error("Can't rollback local modification")
                log.debug(e)
        return False

    def _is_locally_edited_folder(self, doc_pair):
        return doc_pair.local_path.endswith(LOCALLY_EDITED_FOLDER_NAME)

    def _handle_readonly(self, local_client, doc_pair):
        # Don't use readonly on folder for win32 and on Locally Edited
        if (doc_pair.folderish and os.sys.platform == 'win32'
            or self._is_locally_edited_folder(doc_pair)):
            return
        if doc_pair.is_readonly():
            local_client.set_readonly(doc_pair.local_path)
        else:
            local_client.unset_readonly(doc_pair.local_path)