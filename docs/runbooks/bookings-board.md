# Running a day of bookings

Everything here happens in the ops console, under **Bookings** (`/ops/bookings`). Nobody needs the database for any of it.

## Start of the day

Open **Bookings**. It opens on **Needs a person**, oldest first. Work down it:

| What it says | What it means | What to do |
|---|---|---|
| Token in since …: call the owner | The student paid the token more than two hours ago, and the owner hasn't answered. The booking rejects itself at its deadline and refunds the student. | Call the owner. If they say yes, **Confirm for the owner**. If they say no, **Reject for the owner**. |
| Reported …: settle by … | A student says the room isn't as shown. It's to be settled the same day. | Open the report from the booking's page, call the student and the owner, and settle it as refunded or upheld. |
| Move-in due since … | The move-in day has come, and the student hasn't said they've moved in. If they don't, the booking ends as a no-show after the terms' wait. | Call the student. If they've moved in, **Ask the student to say they've moved in**: a text, one a day. Their time to check the room starts only when they say so. |

**Late** marks a timer past its time. The page keeps itself current while it's open.

## Finding a booking

The search box takes a booking's code, a student's phone or part of a PG's name. Choose a status to see only those, each with its count. Bookings still moving list oldest first; the others list newest first.

## On a booking's page

- **What you can do** shows only what's possible now.
- **Whom to call** has both phones. It says if this owner has cancelled bookings after taking them.
- **What happened** is the whole history: each change, who made it, and why.

## The actions

Each change asks why, for the booking's history, then says what it will do before it's sent. None can be undone. The student and the owner never see your reason.

| Action | When | What it does |
|---|---|---|
| Confirm for the owner | The token is in | The student gets a text with the address. Only once the owner has told you they'll take it. |
| Reject for the owner | The token is in | The bed is freed, and the student is told and shown PGs like it. Their token comes back in full. |
| Cancel for the owner | The token is in, or it's confirmed | The same, for an owner who can't take it after all. It counts against the owner on the board. |
| Record a move-out | The stay is active, from the day after the move-in | The booking ends, and the bed is free from the day you give. |

Refunds and the owner's invoice are stubs until payments are built (BUILD_PLAN Phase 6): no money moves yet.
