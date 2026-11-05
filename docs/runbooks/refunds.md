# Refunds

Everything here happens in the ops console. Nobody needs the database, or Razorpay's dashboard, for any of it.

## What happens by itself

A token goes back in full, without anyone doing anything, when:

- the student cancels while they still can for free;
- the owner, or ops for them, rejects or cancels the booking;
- the owner doesn't answer in time;
- ops settle a report that the room isn't as shown as a refund;
- the money arrives after the booking has ended.

The student sees it on their booking, and gets a text once it's processed. A normal refund can take the bank up to 7 working days to show.

## Giving money back by hand

Open the booking under **Bookings**. Under **Payments**, choose **Give money back**, give the amount and why, then confirm. It can't be undone.

Up to ₹5,000 it goes straight away. Above that it waits for a second person.

## Being the second person

Open **Refunds**. It opens on what's waiting. **Approve and send it**, or **Decline** with a reason. You can't approve a refund you asked for. Decline it to withdraw it.

## When one fails

Open **Refunds**, then **Failed**. It says why.

| What it says | What to do |
|---|---|
| Not enough balance | Refunds come out of the Razorpay balance. Add funds in Razorpay's dashboard, then give the money back by hand from the booking. |
| Already refunded | Check the booking's **Payments**. Razorpay may have refunded it already, and if so its webhook will have recorded that. |
| Taken at another gateway | The test site changed gateways after this payment. Nothing was sent, and no real money is involved. |
| Anything else | Check the payment in Razorpay's dashboard, using the ids under **Payments**, then give the money back by hand if it's still owed. |

A failed refund no longer counts against the payment, so the full amount can go back again by hand. Tell the student: their booking says we're looking into it.

## A refund you didn't start

If someone refunds a payment from Razorpay's dashboard, or Razorpay refunds one by itself, its webhook records it on the booking, marked as the gateway's. It counts against what can still go back.
