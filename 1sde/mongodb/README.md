# MongoDB Deep-Dive

This module is the database companion to the Kubernetes guestbook demo in
`k8s/`. That app stores every guest message in a `messages` collection —
here we explain *why* MongoDB is a natural fit, *how* it works under the
hood, and *how to use* every major feature from the shell and from Python.

---

## 1 · What Is MongoDB?

MongoDB is a **document database** — data is stored as self-describing,
schema-flexible **BSON** (Binary JSON) documents rather than rows in fixed
tables.  Each document is a tree of fields and values that can be nested
arbitrarily.

```
// A guestbook message as a MongoDB document
{
  "_id":        ObjectId("6650a1f3c2e4b0001a2b3c4d"),   // auto-generated primary key
  "author":     "ada",
  "text":       "hello from kubernetes",
  "created_at": ISODate("2024-05-24T10:00:00Z"),
  "tags":       ["k8s", "demo"],                         // arrays are first-class
  "meta": {                                              // nested sub-document
    "ip": "10.0.0.5",
    "user_agent": "Mozilla/5.0 ..."
  }
}
```

### BSON vs JSON
- **JSON** is text; **BSON** is a compact binary encoding.
- BSON adds types that JSON lacks: `Date`, `Binary`, `ObjectId`, `Decimal128`,
  `Int32/Int64`, `Regex`, `Timestamp` (for replication).
- The driver converts between Python dicts and BSON transparently.

### Collections vs Tables
| Relational            | MongoDB                        |
|-----------------------|--------------------------------|
| Database              | Database                       |
| Table (fixed columns) | Collection (no required schema)|
| Row                   | Document (BSON dict)           |
| Column                | Field                          |
| Primary key           | `_id` field (any unique value) |
| JOIN                  | `$lookup` in aggregation       |
| Index                 | Index (same concept, richer types)|

### Flexible Schema
Collections have **no enforced schema by default** — documents in the same
collection can have different fields.  This is great for rapid iteration and
polymorphic data.  MongoDB also offers **schema validation** (JSON Schema rules
stored on the collection) when you want to enforce structure.

---

## 2 · Core Concepts

### 2.1 Documents and `_id` / ObjectId

Every document **must** have a unique `_id` field.  If you don't supply one,
the driver generates a 12-byte **ObjectId** automatically:

```
ObjectId("6650a1f3c2e4b0001a2b3c4d")
             |        |    |   |
             └──time  └uid └pid└counter
```

The first 4 bytes encode the Unix timestamp, so ObjectIds are monotonically
increasing (roughly) and can be sorted to get insertion order.

You can use *any* value as `_id` (string, int, UUID …) as long as it is unique
within the collection.  The guestbook lets the driver auto-generate ObjectIds.

### 2.2 CRUD Operations

| Operation          | mongosh                              | PyMongo                              |
|--------------------|--------------------------------------|--------------------------------------|
| Insert one         | `db.col.insertOne({…})`              | `col.insert_one({…})`                |
| Insert many        | `db.col.insertMany([…])`             | `col.insert_many([…])`               |
| Find all           | `db.col.find({})`                    | `col.find({})`                       |
| Find with filter   | `db.col.find({author:"ada"})`        | `col.find({"author":"ada"})`         |
| Find one           | `db.col.findOne({…})`                | `col.find_one({…})`                  |
| Update one         | `db.col.updateOne(filter,{$set:{…}})`| `col.update_one(filter,{"$set":{…}})`|
| Update many        | `db.col.updateMany(filter,update)`   | `col.update_many(filter, update)`    |
| Replace            | `db.col.replaceOne(filter, doc)`     | `col.replace_one(filter, doc)`       |
| Delete one         | `db.col.deleteOne(filter)`           | `col.delete_one(filter)`             |
| Delete many        | `db.col.deleteMany(filter)`          | `col.delete_many(filter)`            |
| Count              | `db.col.countDocuments(filter)`      | `col.count_documents(filter)`        |

### 2.3 Query Operators

Filters are nested dictionaries.  Key operators:

```javascript
// Comparison
{ age: { $gt: 18, $lte: 65 } }   // 18 < age <= 65
{ status: { $in: ["A","B"] } }   // status is A or B
{ status: { $nin: ["C"] } }      // status is not C
{ name: { $ne: "bob" } }         // not equal

// Logical
{ $and: [ {a:1}, {b:2} ] }
{ $or:  [ {a:1}, {b:2} ] }
{ $not: { $gt: 5 } }             // used inside a field condition
{ $nor: [ {a:1}, {b:2} ] }

// Element
{ field: { $exists: true } }
{ field: { $type: "string" } }

// Array
{ tags: "k8s" }                  // array contains "k8s"
{ tags: { $all: ["k8s","demo"] } }  // array contains both
{ tags: { $size: 2 } }           // array has exactly 2 elements
{ "tags.0": "k8s" }              // first element equals "k8s"

// Text (requires a text index)
{ $text: { $search: "kubernetes hello" } }

// Regex
{ author: { $regex: /^ad/i } }
```

### 2.4 Projection

The second argument to `find()` controls which fields are returned:

```javascript
// Return only author and text; suppress _id
db.messages.find({}, { author: 1, text: 1, _id: 0 })

// Return everything except meta
db.messages.find({}, { meta: 0 })
```

`1` means include, `0` means exclude.  You cannot mix inclusions and exclusions
(except for `_id`).

---

## 3 · Indexes

Indexes are data structures (typically B-trees) that let MongoDB find documents
without scanning the whole collection.

### 3.1 Index Types

| Type        | Created with                                  | Use case                                  |
|-------------|-----------------------------------------------|-------------------------------------------|
| Single field| `{field: 1}` (asc) or `{field: -1}` (desc)   | Equality, range, sort on one field        |
| Compound    | `{a: 1, b: -1}`                               | Queries on multiple fields, covered queries|
| Multikey    | Automatic when field is an array              | "contains" queries on array fields        |
| Text        | `{field: "text"}` or `{"$**": "text"}`        | Full-text search across string fields     |
| TTL         | `{created_at:1}` + `expireAfterSeconds: N`    | Auto-delete stale docs (logs, sessions)   |
| Unique      | `{field:1}` + `unique: true`                  | Enforce uniqueness (email, username)      |
| Wildcard    | `{"$**": 1}`                                  | Dynamic / unknown field paths             |
| 2dsphere    | `{loc: "2dsphere"}`                           | Geospatial queries                        |
| Hashed      | `{field: "hashed"}`                           | Even distribution for sharding            |

### 3.2 `explain()` — Understanding Query Plans

```javascript
db.messages.find({author:"ada"}).explain("executionStats")
```

Look for:
- `winningPlan.inputStage.stage: "IXSCAN"` — index used (good).
- `winningPlan.inputStage.stage: "COLLSCAN"` — full scan (add an index!).
- `executionStats.nReturned` vs `totalDocsExamined` — low ratio → poor index.

---

## 4 · Aggregation Pipeline

The aggregation pipeline transforms a stream of documents through a series of
**stages**.  Each stage's output is the next stage's input.

```javascript
db.messages.aggregate([
  { $match:   { author: { $ne: "anonymous" } } },  // filter
  { $group:   { _id: "$author", count: { $sum: 1 }, lastSeen: { $max: "$created_at" } } },
  { $sort:    { count: -1 } },                      // order
  { $project: { _id: 0, author: "$_id", count: 1, lastSeen: 1 } },  // reshape
  { $limit:   10 }
])
```

### Key Stages

| Stage       | What it does                                                  |
|-------------|---------------------------------------------------------------|
| `$match`    | Filter documents (same syntax as `find` query)                |
| `$group`    | Group by `_id` expression; accumulators: `$sum/$avg/$min/$max/$push/$addToSet`|
| `$sort`     | Sort by fields                                                |
| `$project`  | Include/exclude/rename/compute fields; add computed expressions|
| `$limit`    | Keep first N docs                                             |
| `$skip`     | Skip first N docs                                             |
| `$unwind`   | Deconstruct an array field — one doc per array element        |
| `$lookup`   | Left-outer join with another collection                       |
| `$facet`    | Run multiple sub-pipelines in parallel, return combined result|
| `$bucket`   | Group docs into ranges ("buckets")                            |
| `$addFields`| Add computed fields without removing others                   |
| `$replaceRoot`| Replace the root document with a nested sub-document       |
| `$out`      | Write pipeline results to a collection                        |
| `$merge`    | Merge pipeline results into a collection (upsert semantics)   |

### `$lookup` (Join)

```javascript
// Join messages with a hypothetical "users" collection
db.messages.aggregate([
  { $lookup: {
      from:         "users",       // the other collection
      localField:   "author",      // field in messages
      foreignField: "username",    // field in users
      as:           "user_detail"  // name of the array output field
  }},
  { $unwind: { path: "$user_detail", preserveNullAndEmptyArrays: true } }
])
```

### `$facet` (Multi-dimensional Results)

```javascript
// Get stats AND a sample at the same time
db.messages.aggregate([
  { $facet: {
    "stats":  [{ $count: "total" }],
    "byAuthor": [{ $group: { _id: "$author", n: { $sum: 1 } } }, { $sort: {n:-1} }],
    "recent": [{ $sort: { created_at: -1 } }, { $limit: 5 }]
  }}
])
```

---

## 5 · Replica Sets

A **replica set** is a group of `mongod` processes that maintain the same data.

```
     ┌──────────────┐
     │   PRIMARY    │  ← all writes go here
     │   (mongod)   │
     └──────┬───────┘
        oplog
       /       \
┌────────────┐ ┌────────────┐
│ SECONDARY  │ │ SECONDARY  │  ← replicate the primary's oplog
│ (mongod)   │ │ (mongod)   │  ← can serve reads (with preference set)
└────────────┘ └────────────┘
```

### Oplog (Operations Log)

The primary records every write to a special capped collection called the
**oplog** (`local.oplog.rs`).  Secondaries tail the oplog and replay operations
to stay in sync.  The oplog is also the backbone of change streams.

### Elections

If the primary becomes unavailable, the surviving members hold an **election**:
- Each member has a priority (default 1; hidden/delayed members use 0).
- The member with the most up-to-date oplog and majority of votes wins.
- A 3-member set can lose one member and still elect a new primary.
- Election takes a few seconds — writes are refused during this window.

### Why a Replica Set Is Required for Transactions and Change Streams

- **Multi-document ACID transactions** use a distributed commit protocol that
  tracks *"read snapshots"* across nodes; this machinery only exists when
  replica-set metadata (including the oplog) is present.  Even a single-node
  `mongod` must be started with `--replSet` and initiated to use transactions.
- **Change streams** are built on top of the oplog — they provide a
  resumable, ordered cursor over oplog entries.  Without replication, there is
  no oplog, so `watch()` raises an error.

### Write and Read Concerns

| Concern            | Meaning                                                          |
|--------------------|------------------------------------------------------------------|
| `w:1` (default)    | Acknowledged by primary                                          |
| `w:"majority"`     | Acknowledged by majority of voting members (durable on failover)|
| `w:0`              | Fire-and-forget (no acknowledgment)                              |
| `j:true`           | Journaled to disk before ACK (within the ACK'd member)           |
| `r:primary`        | Reads from primary only (consistent)                             |
| `r:secondaryPreferred` | Reads from a secondary if available (lower latency, stale OK) |

---

## 6 · Transactions (Multi-Document ACID)

```python
def transfer_credits(client, from_id, to_id, amount):
    """Move `amount` credits atomically between two documents."""
    with client.start_session() as session:
        def _txn(s):
            accounts = client["bank"]["accounts"]
            accounts.update_one({"_id": from_id}, {"$inc": {"balance": -amount}}, session=s)
            accounts.update_one({"_id": to_id},   {"$inc": {"balance":  amount}}, session=s)
        session.with_transaction(_txn)
```

Key points:
- **Requires** a replica set (or sharded cluster with replica-set shards).
- Default transaction timeout is 60 s.
- Keep transactions short — long transactions hold locks and increase conflict
  probability.
- Prefer single-document operations where possible; they are always atomic.

---

## 7 · Change Streams

Change streams let an application **subscribe to real-time data changes**
without polling:

```python
with col.watch([{"$match": {"operationType": {"$in": ["insert","update"]}}}]) as stream:
    for event in stream:
        print(event["operationType"], event["documentKey"])
```

Use cases: event-driven microservices, cache invalidation, audit logs,
real-time dashboards.

A change stream can be **resumed** after a disconnect using the `resume_after`
or `start_after` token stored in each event — no events are missed.

---

## 8 · Sharding (Horizontal Scale-Out)

When a single replica set's write throughput or storage is exhausted, MongoDB
supports **sharding**: partitioning data across multiple replica sets (shards).

```
Client → mongos (query router)
              ↓
         Config Servers (store chunk metadata)
        /         |         \
   Shard RS 0  Shard RS 1  Shard RS 2
```

- **Shard key**: the field(s) used to partition documents into chunks.
  Choose carefully — a poor shard key causes hot-spots.
- **Chunks**: contiguous ranges of the shard key; MongoDB balances them
  automatically.
- **mongos**: a stateless router that directs queries to the right shard(s).
- Most applications do not need sharding until they hit hundreds of GB or
  thousands of writes/second.

---

## 9 · Schema Design: Embed vs Reference

Unlike a relational database, MongoDB lets you **embed** related data inside a
document (denormalization) or store it in a separate collection and **reference**
it (normalization).

| Criterion              | Embed                              | Reference                         |
|------------------------|------------------------------------|-----------------------------------|
| Relationship           | One-to-few (e.g. 3 phone numbers)  | One-to-many, many-to-many         |
| Access pattern         | Always read together               | Accessed independently            |
| Update frequency       | Rarely updated                     | Frequently updated                |
| Document size growth   | Bounded                            | Unbounded sub-list → reference    |
| Join overhead          | None (already embedded)            | `$lookup` required                |

The **guestbook** uses a simple flat document (no sub-documents needed) because
each message is self-contained.  If we wanted to add threaded replies, we would
likely store replies in a separate `replies` collection and reference the parent
`_id`, because a popular post could accumulate thousands of replies.

---

## 10 · The Guestbook App and MongoDB

The `k8s/app/main.py` FastAPI service writes to the `guestbook` database,
`messages` collection.  Document shape:

```json
{
  "_id":        ObjectId,
  "author":     "string",
  "text":       "string",
  "created_at": ISODate
}
```

Useful queries:

```javascript
// All messages newest-first (matches the /api/messages endpoint)
use guestbook
db.messages.find().sort({_id: -1}).limit(50)

// Count per author
db.messages.aggregate([
  { $group: { _id: "$author", count: { $sum: 1 } } },
  { $sort:  { count: -1 } }
])

// Speed up the /api/messages sort (already exploits ObjectId ordering; a
// compound index would help range queries by author + date)
db.messages.createIndex({ author: 1, created_at: -1 })
```

---

## 11 · Running Everything Locally

### Prerequisites
- Docker + Docker Compose (V2, i.e. `docker compose` not `docker-compose`).
- Python 3.11+, `pip install -r mongodb/examples/requirements.txt`.

### Start the Replica Set

```bash
cd mongodb/
docker compose up -d

# Wait ~10 s for the init container to finish, then verify:
docker compose exec mongo mongosh --eval "rs.status().members.map(m => m.name + ' ' + m.stateStr)"
```

The `mongo-init` one-shot service calls `rs.initiate()` and exits.  After that,
`mongo:7.0` is running as a single-node replica set (`rs0`) on port **27017**,
and Mongo Express (web UI) is available at **http://localhost:8081**.

### Run the Python Examples

```bash
cd mongodb/examples

# Default URI (localhost replica set):
python3 01_crud.py
python3 02_aggregation.py
python3 03_indexes.py
python3 04_transactions.py    # requires replica set
python3 05_change_streams.py  # requires replica set; open another shell to trigger events

# Or run all at once (skips transactions/change-streams if no replica set):
python3 run_all.py

# Custom MongoDB URI:
MONGODB_URI="mongodb://user:pass@host:27017/?replicaSet=rs0" python3 01_crud.py
```

### Run mongosh Scripts

```bash
# Connect and run the sample queries
docker compose exec mongo mongosh guestbook /home/init-replica.js
# (already run automatically by the init container)
docker compose exec mongo mongosh guestbook /mongosh/sample-queries.js
```

---

## 12 · Production and Managed MongoDB

### MongoDB Atlas

[Atlas](https://www.mongodb.com/atlas) is MongoDB's fully managed cloud service:
- Available on AWS, GCP, and Azure.
- Automated backups, point-in-time recovery, online archive.
- Built-in Atlas Search (Lucene-based full-text), Vector Search, Data API.
- Free tier (M0) is enough for small projects.

Connection string drop-in: set `MONGODB_URI` to the Atlas SRV string:
```
mongodb+srv://user:pass@cluster0.abcde.mongodb.net/?retryWrites=true&w=majority
```

### Running on Kubernetes

Two approaches:

1. **StatefulSet (DIY)** — exactly what `k8s/raw/10-mongo.yaml` does.  You
   manage upgrades, replica-set initialization, and backup yourself.  Fine for
   single-replica demos; fragile for production HA.

2. **MongoDB Community Operator** — install via Helm, then declare a
   `MongoDBCommunity` custom resource.  The operator handles replica-set
   initialization, rolling upgrades, user management, and TLS.

   ```bash
   helm repo add mongodb https://mongodb.github.io/helm-charts
   helm install community-operator mongodb/community-operator -n mongodb --create-namespace
   ```

   Then apply a `MongoDBCommunity` manifest to get a 3-member replica set with
   persistent volumes, TLS, and SCRAM authentication wired up automatically.

### Backups

| Strategy                           | Tool / Service                          |
|------------------------------------|-----------------------------------------|
| Logical dump (portable)            | `mongodump` / `mongorestore`            |
| Filesystem snapshot (fast/large)   | Volume snapshots (EBS, Persistent Disk) |
| Continuous cloud backup            | Atlas Backup, Ops Manager               |

Always test restores — a backup you have never restored is an untested backup.

### Security Checklist

- **Authentication**: enable SCRAM-SHA-256 (`--auth`); never expose port 27017
  without authentication.
- **TLS**: use `--tlsMode requireTLS` with a certificate signed by your CA;
  Atlas enforces TLS automatically.
- **Network**: bind to specific IPs (`--bind_ip`); restrict port 27017 with
  firewall/Security Group rules; use Kubernetes NetworkPolicy (see
  `k8s/raw/30-network-policy.yaml`).
- **Least privilege**: create per-application users with only the roles they
  need (`readWrite` on one DB, not `root`).
- **Audit logging**: enable `mongod` audit log in production to track
  administrative actions.
- **Encryption at rest**: use WiredTiger encryption or cloud-provider volume
  encryption.
