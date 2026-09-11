// =============================================================================
// init-replica.js — Replica-Set Initialization Script
//
// PURPOSE
//   Bootstrap a single-node replica set named "rs0".  This script is called
//   automatically by the `mongo-init` Docker service in docker-compose.yml.
//   You can also run it manually:
//
//     mongosh --host localhost:27017 mongodb/mongosh/init-replica.js
//
// HOW A REPLICA SET WORKS
//   - A replica set is a group of mongod processes that replicate the same data.
//   - Exactly ONE member is the PRIMARY at any time; all writes go there.
//   - SECONDARY members replicate the PRIMARY's oplog and can serve reads.
//   - If the PRIMARY goes down, surviving members elect a new PRIMARY
//     (needs a majority: for 3 members, 2 must be alive).
//   - A single-node replica set has no failover, but it unlocks transactions
//     and change streams which require the oplog infrastructure.
// =============================================================================

print("=== Checking current replica set status ===");

let rsStatus;
try {
    rsStatus = rs.status();
    print("Replica set already initialized: " + rsStatus.set);
    print("Members:");
    rsStatus.members.forEach(m => {
        print("  " + m.name + " — " + m.stateStr);
    });
    // Nothing else to do — exit cleanly.
    quit(0);
} catch (e) {
    // Error code 94 = NotYetInitialized — expected on first boot.
    if (e.codeName !== "NotYetInitialized" && e.code !== 94) {
        print("Unexpected error checking rs.status(): " + e);
        quit(1);
    }
    print("Replica set not yet initialized — calling rs.initiate()...");
}

// =============================================================================
// rs.initiate() — define the replica-set configuration.
//
// _id       : the replica-set name; must match --replSet flag passed to mongod.
// members   : list of voting members.
//   _id     : integer ID for this member within the set (0-indexed).
//   host    : "<hostname>:<port>" — use the Docker service name "mongo" when
//             running inside Docker; use "localhost:27017" for bare-metal.
//   priority: (optional) higher = more likely to become PRIMARY in elections.
//   hidden  : (optional) true = never becomes PRIMARY, not listed to clients.
//   votes   : (optional) 1 = participates in elections (default).
// =============================================================================
let cfg = {
    _id: "rs0",
    members: [
        { _id: 0, host: "mongo:27017" }
        // To form a 3-member HA set, add:
        // { _id: 1, host: "mongo1:27017" },
        // { _id: 2, host: "mongo2:27017" }
    ]
};

let result = rs.initiate(cfg);
print("rs.initiate() result: " + JSON.stringify(result));

// Wait a few seconds for the PRIMARY election to complete before we use the set.
print("Waiting for PRIMARY election (up to 30 s)...");
let attempts = 0;
while (attempts < 15) {
    sleep(2000);   // 2 s between checks
    try {
        let isMaster = db.adminCommand({ isMaster: 1 });
        if (isMaster.ismaster) {
            print("PRIMARY elected at: " + isMaster.me);
            break;
        }
        print("  still electing... attempt " + (++attempts));
    } catch (e) {
        print("  waiting for mongod to accept connections... " + e.message);
        attempts++;
    }
}

// =============================================================================
// Seed the guestbook database with sample data so the examples have something
// to query immediately.
// =============================================================================
print("\n=== Seeding guestbook.messages ===");
use("guestbook");

// Drop existing sample docs to make this script idempotent.
db.messages.deleteMany({ _seeded: true });

let seedResult = db.messages.insertMany([
    { author: "ada",     text: "hello from kubernetes",    created_at: new Date("2024-01-15T10:00:00Z"), _seeded: true },
    { author: "alan",    text: "turing was here",          created_at: new Date("2024-01-15T11:30:00Z"), _seeded: true },
    { author: "grace",   text: "bugs are a feature",       created_at: new Date("2024-01-16T09:00:00Z"), _seeded: true },
    { author: "ada",     text: "another message from ada", created_at: new Date("2024-01-16T14:00:00Z"), _seeded: true },
    { author: "linus",   text: "just a hobby project",     created_at: new Date("2024-01-17T08:00:00Z"), _seeded: true },
    { author: "grace",   text: "the only new ship that is entirely safe is one in dry dock", created_at: new Date("2024-01-18T16:00:00Z"), _seeded: true },
]);
print("Inserted " + seedResult.insertedIds.length + " seed messages");

// Create the recommended index (see README §10).
db.messages.createIndex({ author: 1, created_at: -1 }, { name: "author_date_idx" });
print("Created compound index on (author, created_at)");

print("\n=== Replica-set initialization complete ===");
print("Connect to the guestbook database:");
print("  mongosh mongodb://localhost:27017/guestbook?replicaSet=rs0");
