/*!
 * lbvd-offline-db.js
 * ---------------------------------------------------------------------------
 * IndexedDB-backed offline storage and sync client for LBVD web forms.
 *
 * Database
 *   LBVD_Offline_DB
 *     device_info   : local device identity (one "device_id" record)
 *     survey_forms  : locally saved survey records (keyPath: record_uuid)
 *     sync_queue    : immutable payload snapshots (keyPath: operation_uuid)
 *     lookups       : generic cached lookup data (keyPath: key)
 *
 * Public API (also exposed on window.LBVD_OFFLINE)
 *   openLBVDDatabase()
 *   getLBVDDeviceId()
 *   saveLBVDDraft(form, options)
 *   getLBVDForm(recordUuid)
 *   getAllLBVDForms(options)
 *   queueLBVDSync(formOrRecordUuid, options)
 *   getPendingLBVDSync(options)
 *   markLBVDSynced(operationUuid, result)
 *   markLBVDConflict(operationUuid, result)
 *   markLBVDRejected(operationUuid, result)
 *   syncPendingOperationsWithRetry(options)
 *   requestLBVDPersistentStorage()
 *
 * Configuration
 *   window.LBVD_OFFLINE_AUTO_SYNC = false   // disable automatic sync timers
 *   window.LBVD_SYNC_ENDPOINT = '/api/sync'
 *   window.LBVD_OFFLINE_CONFIG = {
 *     syncEndpoint: '/api/sync',
 *     autoSyncMaxDelayMs: 30000,
 *     batchSize: 10
 *   }
 *
 * Request body sent to the sync endpoint:
 *   {
 *     "device_id": "<uuid>",
 *     "sent_at": "<ISO timestamp>",
 *     "operations": [ <immutable operation payload>, ... ]
 *   }
 *
 * Expected response body:
 *   {
 *     "results": [
 *       {
 *         "operation_uuid": "<uuid>",
 *         "status": "accepted" | "duplicate" | "conflict" | "rejected",
 *         "server_version": 1,
 *         "server_form_id": "FORM-0001",
 *         "error_message": null
 *       }
 *     ]
 *   }
 *
 * A network failure (or a response that cannot be understood) leaves the
 * operation in "pending" state.  Local form data is never deleted here.
 * ---------------------------------------------------------------------------
 */
(function (global) {
    'use strict';

    var DB_NAME = 'LBVD_Offline_DB';
    var DB_VERSION = 1;

    var DEVICE_STORE = 'device_info';
    var FORM_STORE = 'survey_forms';
    var QUEUE_STORE = 'sync_queue';
    var LOOKUP_STORE = 'lookups';

    var DEVICE_KEY = 'device_id';
    var DEVICE_UUID_STORAGE_KEY = 'device_uuid';
    var DEFAULT_SYNC_ENDPOINT = '/api/sync';

    var RETRY_DELAYS_MS = [2000, 4000, 8000, 16000, 32000];
    var MAX_ATTEMPTS = 5;
    var DEFAULT_BATCH_SIZE = 10;
    var DEFAULT_AUTO_SYNC_MAX_DELAY_MS = 30000;
    var DEFAULT_REQUEST_TIMEOUT_MS = 30000;

    var FORM_STATUS_DRAFT = 'draft';
    var FORM_STATUS_QUEUED = 'queued';
    var FORM_STATUS_SYNCED = 'synced';
    var FORM_STATUS_CONFLICT = 'conflict';
    var FORM_STATUS_REJECTED = 'rejected';

    var QUEUE_STATUS_PENDING = 'pending';
    var QUEUE_STATUS_PROCESSING = 'processing';
    var QUEUE_STATUS_SYNCED = 'synced';
    var QUEUE_STATUS_CONFLICT = 'conflict';
    var QUEUE_STATUS_REJECTED = 'rejected';
    var QUEUE_STATUS_SUPERSEDED = 'superseded';

    var META_KEYS = {
        record_uuid: true,
        recordUuid: true,
        data: true,
        form_id: true,
        form_type: true,
        status: true,
        created_at: true,
        updated_at: true,
        synced_at: true,
        server_form_id: true,
        server_version: true,
        operation_uuid: true,
        last_error: true,
        deleted: true
    };

    var dbPromise = null;
    var syncInFlight = null;
    var syncTimer = null;
    var syncTimerDue = 0;

    /* =====================================================================
     * Small utilities
     * ===================================================================== */

    function nowIso() {
        return new Date().toISOString();
    }

    function asString(value) {
        return value === null || value === undefined ? '' : String(value);
    }

    function isObject(value) {
        return value !== null && typeof value === 'object';
    }

    function cloneValue(value) {
        if (value === undefined) return undefined;
        if (typeof global.structuredClone === 'function') {
            try {
                return global.structuredClone(value);
            } catch (err) {
                /* fall through to JSON cloning */
            }
        }
        return JSON.parse(JSON.stringify(value));
    }

    function readLocalDeviceUuid() {
        try {
            return global.localStorage.getItem(DEVICE_UUID_STORAGE_KEY);
        } catch (err) {
            return null;
        }
    }

    function writeLocalDeviceUuid(value) {
        try {
            global.localStorage.setItem(DEVICE_UUID_STORAGE_KEY, value);
        } catch (err) {
            /* localStorage can be unavailable in private/embedded contexts */
        }
    }

    function normalizeUuid(value) {
        var text = asString(value).trim().toLowerCase();
        if (!text) return null;
        if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(text)) {
            return null;
        }
        return text;
    }

    function generateUuid() {
        if (global.crypto && typeof global.crypto.randomUUID === 'function') {
            var randomUuid = global.crypto.randomUUID();
            return normalizeUuid(randomUuid) || asString(randomUuid).toLowerCase();
        }

        if (global.crypto && typeof global.crypto.getRandomValues === 'function') {
            var bytes = new Uint8Array(16);
            global.crypto.getRandomValues(bytes);
            bytes[6] = (bytes[6] & 0x0f) | 0x40;
            bytes[8] = (bytes[8] & 0x3f) | 0x80;
            var hex = [];
            for (var i = 0; i < bytes.length; i += 1) {
                hex.push((bytes[i] + 0x100).toString(16).slice(1));
            }
            return (
                hex.slice(0, 4).join('') + '-' +
                hex.slice(4, 6).join('') + '-' +
                hex.slice(6, 8).join('') + '-' +
                hex.slice(8, 10).join('') + '-' +
                hex.slice(10, 16).join('')
            );
        }

        /* Last-resort UUID v4 generator for very old browsers. */
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (ch) {
            var rand = (Math.random() * 16) | 0;
            var value = ch === 'x' ? rand : ((rand & 0x3) | 0x8);
            return value.toString(16);
        });
    }

    function stableStringify(value) {
        var seen = [];

        function walk(current) {
            if (current === null) return 'null';

            var type = typeof current;
            if (type === 'undefined' || type === 'function' || type === 'symbol') {
                return undefined;
            }
            if (type === 'number') {
                return Number.isFinite(current) ? String(current) : 'null';
            }
            if (type === 'boolean') return current ? 'true' : 'false';
            if (type === 'string') return JSON.stringify(current);
            if (type === 'bigint') return JSON.stringify(current.toString());

            if (current instanceof Date) {
                return JSON.stringify(current.toISOString());
            }

            if (type === 'object') {
                if (seen.indexOf(current) !== -1) return '"[Circular]"';
                seen.push(current);

                var output;
                if (Array.isArray(current)) {
                    output = '[' + current.map(function (item) {
                        var encoded = walk(item);
                        return encoded === undefined ? 'null' : encoded;
                    }).join(',') + ']';
                } else {
                    var keys = Object.keys(current).sort();
                    var parts = [];
                    keys.forEach(function (key) {
                        var encoded = walk(current[key]);
                        if (encoded !== undefined) {
                            parts.push(JSON.stringify(key) + ':' + encoded);
                        }
                    });
                    output = '{' + parts.join(',') + '}';
                }

                seen.pop();
                return output;
            }

            return 'null';
        }

        return walk(value);
    }

    function fnv1aHash(text) {
        var hash = 0x811c9dc5;
        for (var i = 0; i < text.length; i += 1) {
            hash ^= text.charCodeAt(i);
            hash = (hash + ((hash << 1) + (hash << 4) + (hash << 7) +
                (hash << 8) + (hash << 24))) >>> 0;
        }
        return hash.toString(16).padStart(8, '0');
    }

    function toHex(buffer) {
        var bytes = new Uint8Array(buffer);
        var parts = [];
        for (var i = 0; i < bytes.length; i += 1) {
            parts.push(bytes[i].toString(16).padStart(2, '0'));
        }
        return parts.join('');
    }

    async function hashPayload(payload) {
        var text = stableStringify(payload);
        if (text === undefined) text = 'null';

        if (global.crypto && global.crypto.subtle &&
            typeof global.TextEncoder === 'function') {
            try {
                var encoded = new global.TextEncoder().encode(text);
                var digest = await global.crypto.subtle.digest('SHA-256', encoded);
                return 'sha256:' + toHex(digest);
            } catch (err) {
                /* Fall back to the deterministic non-crypto hash. */
            }
        }

        return 'fnv1a:' + fnv1aHash(text);
    }

    function readConfig() {
        var config = isObject(global.LBVD_OFFLINE_CONFIG) ? global.LBVD_OFFLINE_CONFIG : {};
        var maxDelay = Number(config.autoSyncMaxDelayMs);
        var batchSize = Number(config.batchSize);

        return {
            syncEndpoint: config.syncEndpoint || global.LBVD_SYNC_ENDPOINT || DEFAULT_SYNC_ENDPOINT,
            autoSyncMaxDelayMs: Number.isFinite(maxDelay) && maxDelay >= 0 ?
                maxDelay : DEFAULT_AUTO_SYNC_MAX_DELAY_MS,
            batchSize: Number.isFinite(batchSize) && batchSize > 0 ?
                Math.floor(batchSize) : DEFAULT_BATCH_SIZE,
            headers: isObject(config.headers) ? config.headers : {}
        };
    }

    function isAutoSyncEnabled() {
        return global.LBVD_OFFLINE_AUTO_SYNC !== false;
    }

    /* =====================================================================
     * IndexedDB low-level helpers
     * ===================================================================== */

    function requestToPromise(request) {
        return new Promise(function (resolve, reject) {
            request.onsuccess = function () { resolve(request.result); };
            request.onerror = function () { reject(request.error); };
        });
    }

    function transactionDone(transaction) {
        return new Promise(function (resolve, reject) {
            transaction.oncomplete = function () { resolve(); };
            transaction.onerror = function () { reject(transaction.error); };
            transaction.onabort = function () {
                reject(transaction.error || new Error('IndexedDB transaction aborted'));
            };
        });
    }

    function openDatabaseRaw() {
        return new Promise(function (resolve, reject) {
            if (!global.indexedDB) {
                reject(new Error('IndexedDB is not supported by this browser.'));
                return;
            }

            var request;
            try {
                request = global.indexedDB.open(DB_NAME, DB_VERSION);
            } catch (err) {
                reject(err);
                return;
            }

            request.onupgradeneeded = function () {
                var db = request.result;

                if (!db.objectStoreNames.contains(DEVICE_STORE)) {
                    db.createObjectStore(DEVICE_STORE, { keyPath: 'key' });
                }

                if (!db.objectStoreNames.contains(FORM_STORE)) {
                    var forms = db.createObjectStore(FORM_STORE, { keyPath: 'record_uuid' });
                    forms.createIndex('status', 'status', { unique: false });
                    forms.createIndex('form_id', 'form_id', { unique: false });
                    forms.createIndex('updated_at', 'updated_at', { unique: false });
                }

                if (!db.objectStoreNames.contains(QUEUE_STORE)) {
                    var queue = db.createObjectStore(QUEUE_STORE, { keyPath: 'operation_uuid' });
                    queue.createIndex('record_uuid', 'record_uuid', { unique: false });
                    queue.createIndex('status', 'status', { unique: false });
                    queue.createIndex('next_attempt_at', 'next_attempt_at', { unique: false });
                    queue.createIndex('created_at', 'created_at', { unique: false });
                }

                if (!db.objectStoreNames.contains(LOOKUP_STORE)) {
                    var lookups = db.createObjectStore(LOOKUP_STORE, { keyPath: 'key' });
                    lookups.createIndex('category', 'category', { unique: false });
                }
            };

            request.onsuccess = function () {
                var db = request.result;
                db.onversionchange = function () {
                    db.close();
                    dbPromise = null;
                };
                resolve(db);
            };

            request.onerror = function () { reject(request.error); };
            request.onblocked = function () {
                reject(new Error('IndexedDB upgrade blocked by another open tab.'));
            };
        });
    }

    function getRecord(db, storeName, key) {
        var transaction = db.transaction(storeName, 'readonly');
        return requestToPromise(transaction.objectStore(storeName).get(key));
    }

    function getAllRecords(db, storeName) {
        var transaction = db.transaction(storeName, 'readonly');
        return requestToPromise(transaction.objectStore(storeName).getAll());
    }

    function putRecord(db, storeName, value) {
        var transaction = db.transaction(storeName, 'readwrite');
        transaction.objectStore(storeName).put(value);
        return transactionDone(transaction).then(function () { return value; });
    }

    function deleteRecord(db, storeName, key) {
        var transaction = db.transaction(storeName, 'readwrite');
        transaction.objectStore(storeName).delete(key);
        return transactionDone(transaction);
    }

    function getAllByIndex(db, storeName, indexName, key) {
        var transaction = db.transaction(storeName, 'readonly');
        var index = transaction.objectStore(storeName).index(indexName);
        var request = key === undefined ? index.getAll() : index.getAll(key);
        return requestToPromise(request);
    }

    function resetStaleProcessingOperations(db) {
        return new Promise(function (resolve, reject) {
            var transaction = db.transaction(QUEUE_STORE, 'readwrite');
            var store = transaction.objectStore(QUEUE_STORE);
            var index = store.index('status');
            var request = index.openCursor(global.IDBKeyRange.only(QUEUE_STATUS_PROCESSING));
            var changedAt = nowIso();

            request.onsuccess = function () {
                var cursor = request.result;
                if (!cursor) return;

                var operation = cursor.value;
                operation.status = QUEUE_STATUS_PENDING;
                operation.next_attempt_at = Date.now();
                operation.updated_at = changedAt;
                operation.last_error = operation.last_error ||
                    'Reset from processing after the application restarted.';
                cursor.update(operation);
                cursor.continue();
            };
            request.onerror = function () { reject(request.error); };
            transaction.oncomplete = function () { resolve(); };
            transaction.onerror = function () { reject(transaction.error); };
            transaction.onabort = function () {
                reject(transaction.error || new Error('Unable to reset processing operations.'));
            };
        });
    }

    async function ensureDeviceRecord(db) {
        var stored = await getRecord(db, DEVICE_STORE, DEVICE_KEY);
        var localUuid = normalizeUuid(readLocalDeviceUuid());
        var storedUuid = stored && normalizeUuid(stored.value);

        /* The login page is authoritative when it has a valid UUID: the server
         * may have created/returned it after the browser first opened this DB. */
        var value = localUuid || storedUuid || generateUuid();
        var now = nowIso();

        if (!stored || stored.value !== value) {
            stored = {
                key: DEVICE_KEY,
                value: value,
                device_id: value,
                source: localUuid ? 'local_storage' : (storedUuid ? 'indexeddb' : 'generated'),
                created_at: stored && stored.created_at ? stored.created_at : now,
                updated_at: now
            };
            await putRecord(db, DEVICE_STORE, stored);
        }

        writeLocalDeviceUuid(value);
        return value;
    }

    /**
     * Open (and lazily initialise) the LBVD IndexedDB database.
     * Leftover "processing" queue items are reset to "pending" exactly once,
     * so the next sync attempt can retry them after a restart.
     */
    function openLBVDDatabase() {
        if (dbPromise) return dbPromise;

        dbPromise = openDatabaseRaw().then(async function (db) {
            try {
                await resetStaleProcessingOperations(db);
            } catch (err) {
                if (global.console) {
                    global.console.warn('[LBVD offline] Could not reset processing operations', err);
                }
            }

            try {
                await ensureDeviceRecord(db);
            } catch (err) {
                if (global.console) {
                    global.console.warn('[LBVD offline] Could not initialise device identity', err);
                }
            }

            if (isAutoSyncEnabled()) {
                scheduleAutoSync();
            }

            return db;
        }).catch(function (err) {
            dbPromise = null;
            throw err;
        });

        return dbPromise;
    }

    /* =====================================================================
     * Device identity
     * ===================================================================== */

    /**
     * Return this browser's stable device UUID.
     * The UUID is generated with crypto.randomUUID(), saved in device_info
     * once, mirrored to localStorage for the login flow, and then reused.
     */
    async function getLBVDDeviceId() {
        var db = await openLBVDDatabase();
        return ensureDeviceRecord(db);
    }

    /* =====================================================================
     * Survey form storage
     * ===================================================================== */

    function extractFormData(form) {
        if (Object.prototype.hasOwnProperty.call(form, 'data')) {
            return cloneValue(form.data);
        }

        var data = {};
        Object.keys(form).forEach(function (key) {
            if (!META_KEYS[key]) {
                data[key] = cloneValue(form[key]);
            }
        });
        return data;
    }

    function dataEquals(left, right) {
        return stableStringify(left) === stableStringify(right);
    }

    /**
     * Save or update a draft.  The record_uuid is generated once for a new
     * form and preserved for every later edit of the same form.
     *
     * form may be either:
     *   { record_uuid, data, form_id, form_type, ... }   // full record
     *   or a flat object of form field values.
     *
     * options: { record_uuid, form_id, form_type, status }
     */
    async function saveLBVDDraft(form, options) {
        if (!isObject(form)) {
            throw new TypeError('saveLBVDDraft(form) expects a form object.');
        }

        options = options || {};
        var db = await openLBVDDatabase();

        var requestedUuid = normalizeUuid(
            options.record_uuid || form.record_uuid || form.recordUuid
        );
        var existing = requestedUuid ? await getRecord(db, FORM_STORE, requestedUuid) : null;
        var recordUuid = requestedUuid || generateUuid();
        var now = nowIso();

        var data = extractFormData(form);
        var existingStatus = existing ? existing.status : null;
        var status = options.status || (existingStatus || FORM_STATUS_DRAFT);

        if (!options.status && existing && existingStatus) {
            var changed = !dataEquals(existing.data, data);
            if (changed && (
                existingStatus === FORM_STATUS_SYNCED ||
                existingStatus === FORM_STATUS_CONFLICT ||
                existingStatus === FORM_STATUS_REJECTED ||
                existingStatus === FORM_STATUS_QUEUED
            )) {
                status = FORM_STATUS_DRAFT;
            }
        }

        var record = {
            record_uuid: recordUuid,
            form_id: options.form_id !== undefined ? options.form_id :
                (form.form_id !== undefined ? form.form_id : (existing ? existing.form_id : null)),
            form_type: options.form_type || form.form_type ||
                (existing ? existing.form_type : 'survey'),
            data: data,
            status: status,
            created_at: (existing && existing.created_at) || form.created_at || now,
            updated_at: now,
            synced_at: (existing && existing.synced_at) || form.synced_at || null,
            server_form_id: form.server_form_id !== undefined ? form.server_form_id :
                (existing ? existing.server_form_id : null),
            server_version: form.server_version !== undefined ? form.server_version :
                (existing ? existing.server_version : null),
            operation_uuid: form.operation_uuid !== undefined ? form.operation_uuid :
                (existing ? existing.operation_uuid : null),
            last_error: form.last_error !== undefined ? form.last_error :
                (existing ? existing.last_error : null),
            deleted: form.deleted !== undefined ? !!form.deleted :
                (existing ? !!existing.deleted : false)
        };

        await putRecord(db, FORM_STORE, record);
        return record;
    }

    /**
     * Read one locally saved form by record_uuid.  Returns null when absent.
     */
    async function getLBVDForm(recordUuid) {
        var normalized = normalizeUuid(recordUuid);
        if (!normalized) return null;
        var db = await openLBVDDatabase();
        return getRecord(db, FORM_STORE, normalized);
    }

    /**
     * Return locally saved forms, newest first.
     *
     * options:
     *   status         string | string[]   filter by form status
     *   form_type      string              filter by form type
     *   includeDeleted boolean             include records marked deleted
     *   limit          number
     *   offset         number
     */
    async function getAllLBVDForms(options) {
        if (typeof options === 'string') {
            options = { status: options };
        }
        options = options || {};

        var db = await openLBVDDatabase();
        var records = await getAllRecords(db, FORM_STORE);
        var statuses = null;

        if (options.status) {
            statuses = Array.isArray(options.status) ? options.status : [options.status];
        }

        records = records.filter(function (record) {
            if (!options.includeDeleted && record.deleted) return false;
            if (statuses && statuses.indexOf(record.status) === -1) return false;
            if (options.form_type && record.form_type !== options.form_type) return false;
            return true;
        });

        records.sort(function (left, right) {
            return asString(right.updated_at).localeCompare(asString(left.updated_at));
        });

        var offset = Number(options.offset) || 0;
        var limit = Number(options.limit);
        if (Number.isFinite(limit) && limit >= 0) {
            records = records.slice(offset, offset + limit);
        } else if (offset > 0) {
            records = records.slice(offset);
        }

        return records;
    }

    /* =====================================================================
     * Sync queue
     * ===================================================================== */

    function buildPayloadBase(record, deviceId, action) {
        return {
            schema_version: 1,
            record_uuid: record.record_uuid,
            form_id: record.form_id || null,
            form_type: record.form_type || 'survey',
            action: action,
            device_id: deviceId,
            data: cloneValue(record.data),
            record_created_at: record.created_at || null,
            record_updated_at: record.updated_at || null
        };
    }

    function determineAction(record, options) {
        if (options.action) return options.action;
        if (record.server_form_id || record.status === FORM_STATUS_SYNCED) {
            return 'update';
        }
        return 'create';
    }

    async function loadRecordForQueue(formOrRecordUuid, options) {
        if (typeof formOrRecordUuid === 'string') {
            var byId = await getLBVDForm(formOrRecordUuid);
            if (!byId) {
                throw new Error('No local form exists for record_uuid ' + formOrRecordUuid);
            }
            return byId;
        }

        if (!isObject(formOrRecordUuid)) {
            throw new TypeError('queueLBVDSync expects a record_uuid or a form object.');
        }

        var explicitUuid = normalizeUuid(
            formOrRecordUuid.record_uuid || formOrRecordUuid.recordUuid
        );

        if (explicitUuid) {
            var existing = await getLBVDForm(explicitUuid);
            if (existing && !Object.prototype.hasOwnProperty.call(formOrRecordUuid, 'data')) {
                return existing;
            }
            if (existing && dataEquals(existing.data, extractFormData(formOrRecordUuid))) {
                return existing;
            }
        }

        return saveLBVDDraft(formOrRecordUuid, options);
    }

    async function supersedeOpenOperations(db, recordUuid, exceptOperationUuid) {
        var operations = await getAllByIndex(db, QUEUE_STORE, 'record_uuid', recordUuid);
        var changedAt = nowIso();

        operations = operations.filter(function (operation) {
            return operation.operation_uuid !== exceptOperationUuid &&
                (operation.status === QUEUE_STATUS_PENDING ||
                    operation.status === QUEUE_STATUS_PROCESSING);
        });

        if (!operations.length) return;

        var transaction = db.transaction(QUEUE_STORE, 'readwrite');
        var store = transaction.objectStore(QUEUE_STORE);
        operations.forEach(function (operation) {
            operation.status = QUEUE_STATUS_SUPERSEDED;
            operation.next_attempt_at = null;
            operation.last_error = 'Superseded by a newer payload for the same form.';
            operation.updated_at = changedAt;
            store.put(operation);
        });
        await transactionDone(transaction);
    }

    async function writeOperationAndForm(db, operation, form) {
        var transaction = db.transaction([QUEUE_STORE, FORM_STORE], 'readwrite');
        transaction.objectStore(QUEUE_STORE).put(operation);
        if (form) {
            transaction.objectStore(FORM_STORE).put(form);
        }
        await transactionDone(transaction);
    }

    /**
     * Queue a form for sync.
     *
     * The payload snapshot is immutable.  If an operation with the same payload
     * already exists, its operation_uuid is reused (retry-safe).  If the form
     * data changed, a new operation_uuid is created and older open operations
     * for that form are marked superseded.
     *
     * Returns the sync_queue record.
     */
    async function queueLBVDSync(formOrRecordUuid, options) {
        options = options || {};
        var db = await openLBVDDatabase();
        var record = await loadRecordForQueue(formOrRecordUuid, options);
        var deviceId = await getLBVDDeviceId();
        var action = determineAction(record, options);

        var payloadBase = buildPayloadBase(record, deviceId, action);
        var payloadHash = await hashPayload(payloadBase);

        if (!options.forceNew) {
            var existingOperations = await getAllByIndex(
                db, QUEUE_STORE, 'record_uuid', record.record_uuid
            );

            var matching = existingOperations.filter(function (operation) {
                return operation.payload_hash === payloadHash &&
                    operation.status !== QUEUE_STATUS_SUPERSEDED;
            }).sort(function (left, right) {
                return asString(right.created_at).localeCompare(asString(left.created_at));
            })[0];

            if (matching) {
                if (record.status !== FORM_STATUS_SYNCED &&
                    record.status !== FORM_STATUS_CONFLICT &&
                    record.status !== FORM_STATUS_REJECTED &&
                    record.operation_uuid !== matching.operation_uuid) {
                    record.status = FORM_STATUS_QUEUED;
                    record.operation_uuid = matching.operation_uuid;
                    record.updated_at = nowIso();
                    await putRecord(db, FORM_STORE, record);
                }

                scheduleAutoSync();
                return matching;
            }
        }

        await supersedeOpenOperations(db, record.record_uuid, null);

        var operationUuid = generateUuid();
        var now = nowIso();
        var payload = Object.assign({ operation_uuid: operationUuid }, payloadBase);

        var operation = {
            operation_uuid: operationUuid,
            record_uuid: record.record_uuid,
            device_id: deviceId,
            action: action,
            payload: payload,
            payload_hash: payloadHash,
            status: QUEUE_STATUS_PENDING,
            attempts: 0,
            max_attempts: MAX_ATTEMPTS,
            next_attempt_at: Date.now(),
            last_attempt_at: null,
            last_error: null,
            server_form_id: null,
            server_version: null,
            server_status: null,
            created_at: now,
            updated_at: now
        };

        record.status = FORM_STATUS_QUEUED;
        record.operation_uuid = operationUuid;
        record.updated_at = now;

        await writeOperationAndForm(db, operation, record);
        scheduleAutoSync();
        return operation;
    }

    function operationIsRetryable(operation) {
        if (operation.status !== QUEUE_STATUS_PENDING) return false;
        var attempts = Number(operation.attempts) || 0;
        var maxAttempts = Number(operation.max_attempts) || MAX_ATTEMPTS;
        /* attempts counts scheduled retries: values 0..maxAttempts are valid.
         * maxAttempts + 1 means the 32s retry also failed, so stop. */
        return attempts <= maxAttempts;
    }

    /**
     * Return pending queue operations whose retry time has arrived.
     *
     * options (or a number):
     *   limit            number   maximum operations to return (default 10)
     *   force            boolean  ignore next_attempt_at / exhausted attempts
     *   includeExhausted boolean  include operations that used all 5 attempts
     *   includeFuture    boolean  include operations scheduled for later
     */
    async function getPendingLBVDSync(options) {
        if (typeof options === 'number') {
            options = { limit: options };
        }
        options = options || {};

        var db = await openLBVDDatabase();
        var operations = await getAllByIndex(
            db, QUEUE_STORE, 'status', QUEUE_STATUS_PENDING
        );
        var now = Date.now();

        operations = operations.filter(function (operation) {
            var attempts = Number(operation.attempts) || 0;
            var maxAttempts = Number(operation.max_attempts) || MAX_ATTEMPTS;

            if (!options.includeExhausted && !options.force && attempts > maxAttempts) {
                return false;
            }
            if (!options.force && !options.includeFuture) {
                var due = operation.next_attempt_at;
                if (due !== null && due !== undefined && Number(due) > now) {
                    return false;
                }
            }
            return true;
        });

        operations.sort(function (left, right) {
            var leftDue = Number(left.next_attempt_at);
            var rightDue = Number(right.next_attempt_at);
            if (!Number.isFinite(leftDue)) leftDue = Number.MAX_SAFE_INTEGER;
            if (!Number.isFinite(rightDue)) rightDue = Number.MAX_SAFE_INTEGER;
            if (leftDue !== rightDue) return leftDue - rightDue;
            return asString(left.created_at).localeCompare(asString(right.created_at));
        });

        var limit = Number(options.limit);
        if (!Number.isFinite(limit) || limit <= 0) limit = DEFAULT_BATCH_SIZE;
        return operations.slice(0, Math.floor(limit));
    }

    async function updateOperationAndForm(operationUuid, operationFields, formFields) {
        var db = await openLBVDDatabase();
        var normalized = normalizeUuid(operationUuid);
        if (!normalized) return false;

        return new Promise(function (resolve, reject) {
            var transaction = db.transaction([QUEUE_STORE, FORM_STORE], 'readwrite');
            var queueStore = transaction.objectStore(QUEUE_STORE);
            var formStore = transaction.objectStore(FORM_STORE);

            var operationRequest = queueStore.get(normalized);
            var formRequest = null;

            operationRequest.onsuccess = function () {
                var operation = operationRequest.result;
                if (!operation) return;

                Object.assign(operation, operationFields, { updated_at: nowIso() });
                queueStore.put(operation);

                if (formFields) {
                    formRequest = formStore.get(operation.record_uuid);
                    formRequest.onsuccess = function () {
                        var form = formRequest.result;
                        if (!form) return;
                        Object.assign(form, formFields, { updated_at: nowIso() });
                        formStore.put(form);
                    };
                }
            };

            transaction.oncomplete = function () { resolve(true); };
            transaction.onerror = function () { reject(transaction.error); };
            transaction.onabort = function () {
                reject(transaction.error || new Error('Unable to update sync operation.'));
            };
        });
    }

    function clearLBVDLocalSessionData() {
        try {
            if (global.sessionStorage) {
                global.sessionStorage.removeItem('lbvdFormData');
            }
        } catch (err) {
            /* sessionStorage may be unavailable */
        }
    }

    async function cleanupConfirmedSync(operationUuid, recordUuid) {
        var db = await openLBVDDatabase();
        var normalizedOp = normalizeUuid(operationUuid);

        return new Promise(function (resolve, reject) {
            var stores = [QUEUE_STORE];
            if (recordUuid) stores.push(FORM_STORE);
            var transaction = db.transaction(stores, 'readwrite');

            if (normalizedOp) {
                transaction.objectStore(QUEUE_STORE).delete(normalizedOp);
            }
            if (recordUuid) {
                transaction.objectStore(FORM_STORE).delete(recordUuid);
            }

            transaction.oncomplete = function () {
                clearLBVDLocalSessionData();
                resolve(true);
            };
            transaction.onerror = function () { reject(transaction.error); };
            transaction.onabort = function () {
                reject(transaction.error || new Error('Unable to clean up synced data.'));
            };
        });
    }

    /**
     * Mark an operation accepted (or duplicate/already-existed) by the server.
     *
     * Per idempotent-sync rules, local record_uuid/session_object data is kept
     * until a confirmed success response is received.  Once accepted or
     * duplicate (already existed in DB) is confirmed, the completed queue item
     * and local draft/session data are removed so the user cannot resend stale
     * data while the server already has the record.
     */
    async function markLBVDSynced(operationUuid, result) {
        result = result || {};
        var db = await openLBVDDatabase();
        var normalized = normalizeUuid(operationUuid);
        var recordUuid = null;

        if (normalized) {
            var operation = await getRecord(db, QUEUE_STORE, normalized);
            if (operation) recordUuid = operation.record_uuid;
        }
        if (!recordUuid && result.record_uuid) {
            recordUuid = normalizeUuid(result.record_uuid);
        }

        await cleanupConfirmedSync(operationUuid, recordUuid);
        return true;
    }

    /**
     * Mark an operation as conflicting with the server copy.
     */
    async function markLBVDConflict(operationUuid, result) {
        result = result || {};
        var message = result.error_message || 'The server reported a conflict.';
        return updateOperationAndForm(
            operationUuid,
            {
                status: QUEUE_STATUS_CONFLICT,
                server_status: result.status || 'conflict',
                server_form_id: result.server_form_id !== undefined ? result.server_form_id : null,
                server_version: result.server_version !== undefined ? result.server_version : null,
                last_error: message,
                next_attempt_at: null
            },
            {
                status: FORM_STATUS_CONFLICT,
                server_form_id: result.server_form_id !== undefined ? result.server_form_id : null,
                server_version: result.server_version !== undefined ? result.server_version : null,
                last_error: message
            }
        );
    }

    /**
     * Mark an operation as rejected by the server.
     */
    async function markLBVDRejected(operationUuid, result) {
        result = result || {};
        var message = result.error_message || 'The server rejected this form.';
        return updateOperationAndForm(
            operationUuid,
            {
                status: QUEUE_STATUS_REJECTED,
                server_status: result.status || 'rejected',
                server_form_id: result.server_form_id !== undefined ? result.server_form_id : null,
                server_version: result.server_version !== undefined ? result.server_version : null,
                last_error: message,
                next_attempt_at: null
            },
            {
                status: FORM_STATUS_REJECTED,
                server_form_id: result.server_form_id !== undefined ? result.server_form_id : null,
                server_version: result.server_version !== undefined ? result.server_version : null,
                last_error: message
            }
        );
    }

    /* =====================================================================
     * Sync execution / retry scheduling
     * ===================================================================== */

    function responseStatus(value) {
        return asString(value).trim().toLowerCase();
    }

    function normalizeResults(body) {
        var results = [];

        if (Array.isArray(body)) {
            results = body;
        } else if (body && Array.isArray(body.results)) {
            results = body.results;
        }

        var byOperation = Object.create(null);
        results.forEach(function (result) {
            if (!isObject(result)) return;
            var operationUuid = result.operation_uuid || result.operationUuid;
            if (operationUuid) {
                byOperation[asString(operationUuid)] = result;
            }
        });
        return byOperation;
    }

    function retryDelayForAttempt(attemptNumber) {
        var index = Math.min(
            Math.max(attemptNumber - 1, 0),
            RETRY_DELAYS_MS.length - 1
        );
        var base = RETRY_DELAYS_MS[index];
        var jitter = 0.8 + (Math.random() * 0.4); /* +/- 20% */
        return Math.round(base * jitter);
    }

    async function claimOperations(db, operations) {
        if (!operations.length) return [];

        var transaction = db.transaction(QUEUE_STORE, 'readwrite');
        var store = transaction.objectStore(QUEUE_STORE);
        var claimed = [];
        var attemptedAt = nowIso();

        operations.forEach(function (operation) {
            var claimedOperation = Object.assign({}, operation, {
                status: QUEUE_STATUS_PROCESSING,
                last_attempt_at: attemptedAt,
                updated_at: attemptedAt
            });
            store.put(claimedOperation);
            claimed.push(claimedOperation);
        });

        await transactionDone(transaction);
        return claimed;
    }

    async function recordRetryFailure(operation, errorMessage) {
        var attempts = (Number(operation.attempts) || 0) + 1;
        var maxAttempts = Number(operation.max_attempts) || MAX_ATTEMPTS;
        /* attempts is the retry number: 1 -> 2s, 2 -> 4s, ...
         * 5 -> 32s, and 6 -> no further automatic retry. */
        var exhausted = attempts > maxAttempts;
        var retryAt = exhausted ? null : Date.now() + retryDelayForAttempt(attempts);

        await updateOperationAndForm(
            operation.operation_uuid,
            {
                status: QUEUE_STATUS_PENDING,
                attempts: attempts,
                next_attempt_at: retryAt,
                last_error: errorMessage || 'Network error while syncing.',
                exhausted: exhausted
            },
            null
        );

        return retryAt;
    }

    function buildSyncRequest(deviceId, operations) {
        return {
            device_id: deviceId,
            sent_at: nowIso(),
            operations: operations.map(function (operation) {
                return operation.payload;
            })
        };
    }

    async function postSyncBatch(endpoint, requestBody, options, config) {
        var headers = Object.assign(
            { 'Content-Type': 'application/json', 'Accept': 'application/json' },
            config.headers || {},
            options.headers || {}
        );

        var fetchOptions = {
            method: 'POST',
            headers: headers,
            credentials: options.credentials || 'same-origin',
            body: JSON.stringify(requestBody)
        };

        var timeoutMs = Number(options.timeoutMs);
        if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
            timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS;
        }

        var controller = null;
        var timer = null;
        if (typeof global.AbortController === 'function') {
            controller = new global.AbortController();
            fetchOptions.signal = controller.signal;
            timer = global.setTimeout(function () {
                controller.abort();
            }, timeoutMs);
        }

        try {
            var response = await global.fetch(endpoint, fetchOptions);
            var text = await response.text();
            var body = null;

            if (text) {
                try {
                    body = JSON.parse(text);
                } catch (err) {
                    body = text;
                }
            }

            if (!response.ok) {
                var detail = body && typeof body === 'object' ?
                    (body.detail || body.error || body.message) : body;
                throw new Error(
                    'Sync request failed with HTTP ' + response.status +
                    (detail ? ': ' + asString(detail) : '')
                );
            }

            return body;
        } finally {
            if (timer !== null) global.clearTimeout(timer);
        }
    }

    async function processSyncBatch(db, operations, options, config, summary) {
        var claimed = await claimOperations(db, operations);
        if (!claimed.length) return { networkError: false, sent: 0 };

        summary.sent += claimed.length;
        summary.batches += 1;

        var deviceId = await getLBVDDeviceId();
        var configuredEndpoint = options.endpoint || config.syncEndpoint;
        var endpoint = typeof configuredEndpoint === 'function' ?
            configuredEndpoint(claimed) : configuredEndpoint;

        var body;
        try {
            body = await postSyncBatch(
                endpoint,
                buildSyncRequest(deviceId, claimed),
                options,
                config
            );
        } catch (err) {
            var message = err && err.message ? err.message : 'Network error while syncing.';
            summary.networkError = message;

            for (var f = 0; f < claimed.length; f += 1) {
                try {
                    await recordRetryFailure(claimed[f], message);
                    summary.failed += 1;
                } catch (updateError) {
                    summary.failed += 1;
                    if (global.console) {
                        global.console.error('[LBVD offline] Failed to record retry', updateError);
                    }
                }
            }

            return { networkError: true, sent: claimed.length };
        }

        var results = normalizeResults(body);

        for (var i = 0; i < claimed.length; i += 1) {
            var operation = claimed[i];
            var result = results[operation.operation_uuid];

            if (!result) {
                await recordRetryFailure(
                    operation,
                    'The sync response did not include a result for this operation.'
                );
                summary.failed += 1;
                continue;
            }

            var status = responseStatus(result.status);

            try {
                if (status === 'accepted' || status === 'duplicate') {
                    var message = result.error_message || result.message ||
                        (status === 'duplicate'
                            ? 'ဤအချက်အလက်ကို ဒေတာဘေ့စ်တွင် သိမ်းဆည်းပြီးသားဖြစ်ပါသည်။'
                            : 'အချက်အလက်ကို အောင်မြင်စွာ သိမ်းဆည်းပြီးပါပြီ။');
                    await markLBVDSynced(operation.operation_uuid, result);
                    if (status === 'duplicate') {
                        summary.duplicate += 1;
                        summary.alreadyExisted += 1;
                        if (summary.messages) summary.messages.alreadyExisted.push({
                            operation_uuid: operation.operation_uuid,
                            record_uuid: operation.record_uuid,
                            server_form_id: result.server_form_id || null,
                            message: message
                        });
                    } else {
                        summary.accepted += 1;
                        if (summary.messages) summary.messages.inserted.push({
                            operation_uuid: operation.operation_uuid,
                            record_uuid: operation.record_uuid,
                            server_form_id: result.server_form_id || null,
                            message: message
                        });
                    }
                } else if (status === 'conflict') {
                    await markLBVDConflict(operation.operation_uuid, result);
                    summary.conflict += 1;
                } else if (status === 'rejected') {
                    await markLBVDRejected(operation.operation_uuid, result);
                    summary.rejected += 1;
                } else {
                    await recordRetryFailure(
                        operation,
                        'Unknown sync status: ' + asString(result.status)
                    );
                    summary.failed += 1;
                }
            } catch (updateError) {
                summary.failed += 1;
                if (global.console) {
                    global.console.error('[LBVD offline] Failed to apply sync result', updateError);
                }
            }
        }

        return { networkError: false, sent: claimed.length };
    }

    async function getRetryablePending(db) {
        var operations = await getAllByIndex(db, QUEUE_STORE, 'status', QUEUE_STATUS_PENDING);
        return operations.filter(operationIsRetryable);
    }

    function scheduleSyncAt(when) {
        var target = Math.max(Date.now() + 250, Number(when) || Date.now());
        if (syncTimer !== null && syncTimerDue <= target) return;

        if (syncTimer !== null) {
            global.clearTimeout(syncTimer);
        }

        syncTimerDue = target;
        syncTimer = global.setTimeout(async function () {
            syncTimer = null;
            syncTimerDue = 0;
            try {
                await syncPendingOperationsWithRetry({ fromTimer: true });
            } catch (err) {
                if (global.console) {
                    global.console.warn('[LBVD offline] Automatic sync failed', err);
                }
            }
        }, Math.max(0, target - Date.now()));
    }

    function scheduleAutoSync() {
        if (!isAutoSyncEnabled()) return;
        var config = readConfig();
        var delay = Math.floor(Math.random() * (config.autoSyncMaxDelayMs + 1));
        scheduleSyncAt(Date.now() + delay);
    }

    async function scheduleNextSync(db) {
        var pending = await getRetryablePending(db);
        var now = Date.now();
        var nextAt = Infinity;

        pending.forEach(function (operation) {
            var due = Number(operation.next_attempt_at);
            if (!Number.isFinite(due)) due = now;
            if (due < nextAt) nextAt = due;
        });

        if (pending.length && nextAt !== Infinity) {
            /* Retries always continue, even when periodic auto sync is off. */
            scheduleSyncAt(nextAt);
        }

        if (isAutoSyncEnabled()) {
            var config = readConfig();
            var randomDelay = Math.floor(Math.random() * (config.autoSyncMaxDelayMs + 1));
            scheduleSyncAt(now + randomDelay);
        }
    }

    /**
     * Send due pending operations in batches of at most 10.
     *
     * Network errors keep operations pending and schedule the next attempt at
     * 2s, 4s, 8s, 16s or 32s (+/- 20% jitter), up to 5 attempts.  The function
     * returns after the current pass; future attempts are scheduled with
     * timers and also survive reloads because retry state is in IndexedDB.
     *
     * options:
     *   endpoint     string/function  override sync endpoint
     *   batchSize    number           max operations per request (default 10)
     *   force        boolean          include operations whose retry time is later
     *   headers      object           extra request headers
     *   credentials  string           fetch credentials mode
     *   timeoutMs    number           request timeout
     */
    async function syncPendingOperationsWithRetry(options) {
        options = options || {};

        if (syncInFlight) return syncInFlight;

        syncInFlight = (async function () {
            var config = readConfig();
            var db = await openLBVDDatabase();
            var requestedBatch = Number(options.batchSize);
            var batchSize = Number.isFinite(requestedBatch) && requestedBatch > 0 ?
                Math.floor(requestedBatch) : config.batchSize;

            var summary = {
                batches: 0,
                sent: 0,
                accepted: 0,
                duplicate: 0,
                alreadyExisted: 0,
                conflict: 0,
                rejected: 0,
                failed: 0,
                networkError: null,
                pending: 0,
                nextRetryAt: null,
                messages: {
                    inserted: [],
                    alreadyExisted: []
                }
            };

            var forceFirstBatch = !!options.force;
            var maxBatches = 100;

            while (summary.batches < maxBatches) {
                var operations = await getPendingLBVDSync({
                    limit: batchSize,
                    force: forceFirstBatch
                });
                forceFirstBatch = false;

                if (!operations.length) break;

                var batchResult = await processSyncBatch(
                    db, operations, options, config, summary
                );

                if (batchResult.networkError) break;
                if (!batchResult.sent) break;
            }

            var remaining = await getRetryablePending(db);
            summary.pending = remaining.length;

            var earliest = Infinity;
            remaining.forEach(function (operation) {
                var due = Number(operation.next_attempt_at);
                if (!Number.isFinite(due)) due = Date.now();
                if (due < earliest) earliest = due;
            });
            if (earliest !== Infinity) summary.nextRetryAt = earliest;

            await scheduleNextSync(db);
            return summary;
        })();

        try {
            return await syncInFlight;
        } finally {
            syncInFlight = null;
        }
    }

    /* =====================================================================
     * Persistent storage + lookup helpers
     * ===================================================================== */

    /**
     * Ask the browser to make this origin's storage persistent.
     * Returns true when storage is/was granted persistence, otherwise false.
     */
    async function requestLBVDPersistentStorage() {
        try {
            if (!global.navigator || !global.navigator.storage) return false;

            if (typeof global.navigator.storage.persisted === 'function') {
                var alreadyPersistent = await global.navigator.storage.persisted();
                if (alreadyPersistent) return true;
            }

            if (typeof global.navigator.storage.persist === 'function') {
                return await global.navigator.storage.persist();
            }
        } catch (err) {
            if (global.console) {
                global.console.warn('[LBVD offline] Persistent storage request failed', err);
            }
        }

        return false;
    }

    /**
     * Cache a lookup value (states, districts, townships, villages, etc.).
     */
    async function putLBVDLookup(key, value, category) {
        var db = await openLBVDDatabase();
        var now = nowIso();
        var existing = await getRecord(db, LOOKUP_STORE, asString(key));

        var record = {
            key: asString(key),
            category: category || (existing && existing.category) || null,
            value: cloneValue(value),
            created_at: (existing && existing.created_at) || now,
            updated_at: now
        };

        await putRecord(db, LOOKUP_STORE, record);
        return record;
    }

    /**
     * Read a cached lookup value.
     */
    async function getLBVDLookup(key) {
        var db = await openLBVDDatabase();
        var record = await getRecord(db, LOOKUP_STORE, asString(key));
        return record ? record.value : null;
    }

    /**
     * Read every lookup in a category (omit category for all lookups).
     */
    async function getAllLBVDLookups(category) {
        var db = await openLBVDDatabase();
        var records = category === undefined ?
            await getAllRecords(db, LOOKUP_STORE) :
            await getAllByIndex(db, LOOKUP_STORE, 'category', category);
        return records.map(function (record) { return record.value; });
    }

    /* =====================================================================
     * Public exports
     * ===================================================================== */

    var api = {
        DB_NAME: DB_NAME,
        DB_VERSION: DB_VERSION,
        stores: {
            device_info: DEVICE_STORE,
            survey_forms: FORM_STORE,
            sync_queue: QUEUE_STORE,
            lookups: LOOKUP_STORE
        },
        retryDelaysMs: RETRY_DELAYS_MS.slice(),
        maxAttempts: MAX_ATTEMPTS,
        openLBVDDatabase: openLBVDDatabase,
        getLBVDDeviceId: getLBVDDeviceId,
        saveLBVDDraft: saveLBVDDraft,
        getLBVDForm: getLBVDForm,
        getAllLBVDForms: getAllLBVDForms,
        queueLBVDSync: queueLBVDSync,
        getPendingLBVDSync: getPendingLBVDSync,
        markLBVDSynced: markLBVDSynced,
        markLBVDConflict: markLBVDConflict,
        markLBVDRejected: markLBVDRejected,
        syncPendingOperationsWithRetry: syncPendingOperationsWithRetry,
        requestLBVDPersistentStorage: requestLBVDPersistentStorage,
        clearLBVDLocalSessionData: clearLBVDLocalSessionData,
        putLBVDLookup: putLBVDLookup,
        getLBVDLookup: getLBVDLookup,
        getAllLBVDLookups: getAllLBVDLookups
    };

    global.LBVD_OFFLINE = api;

    global.openLBVDDatabase = openLBVDDatabase;
    global.getLBVDDeviceId = getLBVDDeviceId;
    global.saveLBVDDraft = saveLBVDDraft;
    global.getLBVDForm = getLBVDForm;
    global.getAllLBVDForms = getAllLBVDForms;
    global.queueLBVDSync = queueLBVDSync;
    global.getPendingLBVDSync = getPendingLBVDSync;
    global.markLBVDSynced = markLBVDSynced;
    global.markLBVDConflict = markLBVDConflict;
    global.markLBVDRejected = markLBVDRejected;
    global.syncPendingOperationsWithRetry = syncPendingOperationsWithRetry;
    global.requestLBVDPersistentStorage = requestLBVDPersistentStorage;
    global.clearLBVDLocalSessionData = clearLBVDLocalSessionData;
    global.putLBVDLookup = putLBVDLookup;
    global.getLBVDLookup = getLBVDLookup;
    global.getAllLBVDLookups = getAllLBVDLookups;
})(typeof window !== 'undefined' ? window : globalThis);
