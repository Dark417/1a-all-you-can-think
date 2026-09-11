// =============================================================================
// sample-queries.js — mongosh Tour of MongoDB Features
//
// PURPOSE
//   A self-contained guided tour of MongoDB's most important operations,
//   designed to run against the guestbook database seeded by init-replica.js.
//   Comments explain WHAT each operation does and WHY you would use it.
//
// RUN
//   # Inside Docker:
//   docker compose exec mongo mongosh guestbook /mongosh/sample-queries.js
//
//   # Or directly (if mongosh is installed locally):
//   mongosh "mongodb://localhost:27017/guestbook?replicaSet=rs0" \
//           mongodb/mongosh/sample-queries.js
// =============================================================================

print("\n" + "=".repeat(60));
print(" MongoDB Feature Tour — guestbook database");
print("=".repeat(60));

// Connect to the guestbook database.
// `use()` in mongosh switches the implicit `db` variable.
use("guestbook");

// =============================================================================
// SECTION 1 — CRUD (Create / Read / Update / Delete)
// =============================================================================
print("\n--- 1. CRUD ---");

// --- INSERT ---
// insertOne: add a single document; MongoDB generates _id automatically.
let ins1 = db.messages.insertOne({
    author: "margaret",
    text:   "we choose to go to the moon",
    created_at: new Date()
});
print("insertOne _id: " + ins1.insertedId);

// insertMany: batch insert — more efficient than multiple insertOne calls.
let ins2 = db.messages.insertMany([
    { author: "rita",   text: "software is eating the world", created_at: new Date() },
    { author: "margaret", text: "to err is human", created_at: new Date() }
]);
print("insertMany count: " + ins2.insertedIds.length);

// --- READ ---
// find(): returns a cursor; toArray() or forEach() materializes it.
print("\nAll messages (newest first, limit 5):");
db.messages.find({})
    .sort({ _id: -1 })   // ObjectId encodes insert time → sort proxy
    .limit(5)
    .forEach(doc => print("  " + doc.author + ": " + doc.text));

// find() with a filter — equality match.
print("\nMessages by 'ada':");
db.messages.find({ author: "ada" })
    .forEach(doc => print("  " + doc.text));

// find() with a query operator.
// $regex matches author names starting with "m" (case-insensitive).
print("\nAuthors starting with 'm':");
db.messages.find({ author: { $regex: /^m/i } })
    .forEach(doc => print("  " + doc.author + ": " + doc.text));

// Projection: only return author + text, suppress _id.
print("\nProjection — author & text only:");
db.messages.find({}, { _id: 0, author: 1, text: 1 })
    .limit(3)
    .forEach(doc => printjson(doc));

// findOne: first matching document or null.
let oneDoc = db.messages.findOne({ author: "grace" });
print("\nfindOne (grace): " + (oneDoc ? oneDoc.text : "not found"));

// countDocuments: accurate count with a filter (uses index if available).
let count = db.messages.countDocuments({ author: { $in: ["ada", "grace"] } });
print("\nMessages from ada OR grace: " + count);

// --- UPDATE ---
// $set: update specific fields without replacing the entire document.
// { returnDocument: "after" } returns the document after the update.
let upd = db.messages.findOneAndUpdate(
    { author: "rita", text: { $regex: /eating/ } },
    { $set: { tags: ["tech", "future"], updated: true } },
    { returnDocument: "after" }
);
print("\nAfter $set update on rita's doc:");
printjson(upd);

// $inc: atomically increment / decrement a numeric field.
// $push: append a value to an array field.
db.messages.updateOne(
    { author: "margaret" },
    {
        $inc:  { view_count: 1 },      // create field if it doesn't exist
        $push: { tags: "inspirational" }
    }
);

// updateMany: update every matching document.
let updMany = db.messages.updateMany(
    { tags: { $exists: false } },     // docs without a 'tags' field
    { $set: { tags: [] } }            // initialize to empty array
);
print("\nupdateMany (add tags:[]): modified " + updMany.modifiedCount + " docs");

// Upsert: insert if no document matches the filter.
db.messages.updateOne(
    { author: "django", text: "upserted doc" },
    { $setOnInsert: { created_at: new Date(), author: "django", text: "upserted doc" } },
    { upsert: true }
);
print("Upsert done (check for 'django' doc)");

// --- DELETE ---
let del1 = db.messages.deleteOne({ author: "django" });
print("\ndeleteOne 'django': deleted " + del1.deletedCount);

let delMany = db.messages.deleteMany({ text: { $regex: /upsert/ } });
print("deleteMany /upsert/: deleted " + delMany.deletedCount);


// =============================================================================
// SECTION 2 — INDEXES
// =============================================================================
print("\n--- 2. Indexes ---");

// Single-field ascending index — speeds up queries filtering / sorting by author.
db.messages.createIndex({ author: 1 }, { name: "author_asc" });
print("Created single-field index on 'author'");

// Compound index — covers queries that filter on author AND sort by created_at.
// Index prefix rule: this index also speeds up queries on { author } alone,
// but NOT queries on { created_at } alone.
db.messages.createIndex(
    { author: 1, created_at: -1 },
    { name: "author_date_compound" }
);
print("Created compound index on (author, created_at DESC)");

// Unique index — enforce no two documents share the same value.
// We add it on a separate 'usernames' collection to avoid conflicts.
db.usernames.drop();
db.usernames.insertMany([{ username: "ada" }, { username: "grace" }]);
db.usernames.createIndex({ username: 1 }, { unique: true, name: "username_unique" });
print("Created unique index on usernames.username");

// Text index — full-text search across the 'text' field.
// Only one text index allowed per collection.
db.messages.createIndex({ text: "text" }, { name: "text_search" });
print("Created text index on 'text'");

// TTL (Time-To-Live) index — MongoDB automatically deletes documents once
// `created_at` is older than `expireAfterSeconds`.
// Here we demo it on a separate 'sessions' collection (messages should persist).
db.sessions.drop();
db.sessions.insertOne({ token: "abc123", created_at: new Date() });
db.sessions.createIndex(
    { created_at: 1 },
    { expireAfterSeconds: 3600, name: "session_ttl" }   // expire after 1 hour
);
print("Created TTL index on sessions.created_at (expireAfterSeconds: 3600)");

// List all indexes on messages.
print("\nIndexes on messages collection:");
db.messages.getIndexes().forEach(idx => {
    print("  " + idx.name + " — key: " + JSON.stringify(idx.key));
});

// explain() — inspect whether a query uses an index or does a full scan.
print("\nexplain() for find({author:'ada'}):");
let plan = db.messages.find({ author: "ada" }).explain("executionStats");
print("  Winning stage: " + plan.queryPlanner.winningPlan.inputStage.stage);
print("  Docs examined: " + plan.executionStats.totalDocsExamined);
print("  Docs returned: " + plan.executionStats.nReturned);
// IXSCAN = index scan (good); COLLSCAN = full collection scan (add an index).


// =============================================================================
// SECTION 3 — AGGREGATION PIPELINE
// =============================================================================
print("\n--- 3. Aggregation Pipeline ---");

// $match + $group + $sort: classic "top N per group" pattern.
print("\nMessage count per author (top 5):");
db.messages.aggregate([
    // Stage 1: only include real messages (skip our seed docs if desired)
    { $match: { author: { $exists: true } } },
    // Stage 2: group by author, count messages
    { $group: { _id: "$author", count: { $sum: 1 }, lastSeen: { $max: "$created_at" } } },
    // Stage 3: sort by count descending
    { $sort: { count: -1 } },
    // Stage 4: only top 5
    { $limit: 5 },
    // Stage 5: rename _id → author for readability
    { $project: { _id: 0, author: "$_id", count: 1, lastSeen: 1 } }
]).forEach(doc => print("  " + doc.author + ": " + doc.count + " msgs"));

// $unwind: deconstruct an array field — each element becomes its own document.
// Useful for then grouping or filtering on individual array elements.
print("\nFlattened tags (with $unwind):");
db.messages.aggregate([
    { $match:  { tags: { $exists: true, $ne: [] } } },
    { $unwind: "$tags" },             // one doc per tag
    { $group:  { _id: "$tags", count: { $sum: 1 } } },
    { $sort:   { count: -1 } }
]).forEach(doc => print("  #" + doc._id + " (" + doc.count + ")"));

// $lookup: left-outer join between messages and usernames collections.
// This is the aggregation equivalent of SQL JOIN.
print("\n$lookup — join messages with usernames:");
db.messages.aggregate([
    { $lookup: {
        from:         "usernames",    // the collection to join
        localField:   "author",       // field in messages
        foreignField: "username",     // field in usernames
        as:           "user_detail"   // output array field name
    }},
    { $match: { user_detail: { $ne: [] } } },  // only keep matched docs
    { $project: { _id: 0, author: 1, text: { $substr: ["$text", 0, 30] }, has_account: { $gt: [{ $size: "$user_detail" }, 0] } } },
    { $limit: 4 }
]).forEach(doc => printjson(doc));

// $facet: run multiple sub-pipelines in parallel and return a single document.
// Perfect for "stats + sample + histogram" in one round trip.
print("\n$facet — multi-dimensional stats in one query:");
let facetResult = db.messages.aggregate([
    { $facet: {
        total:    [{ $count: "n" }],
        byAuthor: [
            { $group: { _id: "$author", n: { $sum: 1 } } },
            { $sort:  { n: -1 } },
            { $limit: 3 }
        ],
        recent:   [
            { $sort:  { created_at: -1 } },
            { $limit: 2 },
            { $project: { _id: 0, author: 1, text: { $substr: ["$text", 0, 40] } } }
        ]
    }}
]).next();
print("  Total docs: " + facetResult.total[0].n);
print("  Top authors: " + facetResult.byAuthor.map(d => d._id + "(" + d.n + ")").join(", "));
print("  Recent:");
facetResult.recent.forEach(d => print("    " + d.author + ": " + d.text));


// =============================================================================
// SECTION 4 — TRANSACTIONS (requires replica set)
// =============================================================================
print("\n--- 4. Transactions ---");

// Set up a bank-accounts collection for the transfer demo.
db.accounts.drop();
db.accounts.insertMany([
    { _id: "alice", balance: 500 },
    { _id: "bob",   balance: 200 }
]);

// A multi-document transaction — either both updates commit or neither does.
// This is the core ACID guarantee for cross-document writes.
let session = db.getMongo().startSession();
print("Starting transaction to transfer 100 from alice to bob...");
session.startTransaction({
    readConcern:  { level: "snapshot" },   // read a consistent snapshot
    writeConcern: { w: "majority" }         // durable on majority of members
});
try {
    let accounts = session.getDatabase("guestbook").accounts;
    accounts.updateOne({ _id: "alice" }, { $inc: { balance: -100 } });
    accounts.updateOne({ _id: "bob"   }, { $inc: { balance:  100 } });
    session.commitTransaction();
    print("Transaction committed.");
} catch (e) {
    session.abortTransaction();
    print("Transaction ABORTED: " + e);
} finally {
    session.endSession();
}

print("Balances after transfer:");
db.accounts.find({}).forEach(a => print("  " + a._id + ": " + a.balance));


// =============================================================================
// SECTION 5 — CHANGE STREAMS (requires replica set; shown as setup only)
// =============================================================================
print("\n--- 5. Change Streams (overview) ---");
print("Change streams must be consumed in application code (see 05_change_streams.py).");
print("In mongosh, you can open a stream like this:");
print("  var cs = db.messages.watch([{$match:{operationType:{$in:['insert','update']}}}]);");
print("  cs.next()   // blocks until an event arrives");
print("  // In another shell: db.messages.insertOne({author:'test',text:'ping',created_at:new Date()})");

print("\n" + "=".repeat(60));
print(" Tour complete.  Run the Python examples for more:");
print("   python3 mongodb/examples/01_crud.py");
print("=".repeat(60) + "\n");
