# Product context

This file explains the business so the code makes the right calls. It summarises the founders' research plan and planning discussions up to 18 October 2026. When this file and a code comment disagree, this file wins; when this file and the founders disagree, the founders win and this file gets updated.

Founders' full research plan (private, for humans): https://claude.ai/code/artifact/4a5d3517-09fe-498e-8e43-d07cfbf27102

---

## 1. The idea

An online platform for booking PG (paying guest) beds in Delhi NCR, started by two founders. Students and parents find verified PGs on a map, book a visit, reserve a bed with a small refundable token, and move in. Owners pay a one-time placement fee for each tenant the platform brings; students pay nothing.

What makes it different from listing sites and brokers:
- **Verified listings**: a field agent visits every building, checks safety and takes the photos.
- **Safe booking**: the student's token is protected until they have moved in and checked the room.
- **Owner-side dynamic pricing**: owners earn more in peak season, and all of that extra goes to them.

The brand name is undecided (candidates so far: Berth Stays, Keyday, Stayproof). Keep it in config.

## 2. Who uses it

| User | What they need |
|---|---|
| Students (17–25), many from outside Delhi | A safe, verified bed near their college or coaching hub, within budget, without being scammed |
| Parents | Confidence the PG is safe; often the ones who decide and pay |
| Working professionals in Gurugram and Noida | Same, and they keep demand steady outside the student season |
| PG owners (typically 10–50 beds) | Full beds, better prices in peak season, little admin, getting paid on time |
| Field agents | Verify buildings, run visits, capture photos and GPS |
| Ops / admin (the founders at first) | Run listings, visits, bookings, disputes and refunds |

Demand is seasonal. Most student demand lands between June and August, peaking around DU's first allocation list in mid-July. Everything must be live, verified and load-tested before June 2027.

Version 1 is a **mobile website that installs as an app (PWA)**, not App Store apps. Students from other cities find PGs through Google, Instagram and seniors.

## 3. How money works

### Students
- Pay **no platform fee**. Never add a booking, convenience or service fee on the student side.
- Pay a **refundable token**, ₹2,000 by default (₹1,000–2,000 range). The token counts toward the first month's rent.
- Pay the rest of the first month's rent at move-in: to the owner directly at first, through the platform later.
- Keep tokens at or under ₹2,000: from 15 October 2026, UPI payments to merchants above ₹2,000 carry a 0.4% fee that can't be passed on to the customer.

### Owners
- Pay a **one-time placement fee of 30% of one month's listed rent** for each tenant placed.
- GST at 18% applies to the fee. The founders haven't decided whether the 30% includes GST:
  - Exclusive (default): at ₹10,000 rent the owner pays ₹3,000 + ₹540 GST = ₹3,540, which is 35.4% of a month's rent.
  - Inclusive: the owner pays ₹3,000 and the platform keeps ₹2,542 net, which is 25.4%.
- Long-stay PG rent up to ₹20,000 a month is GST-exempt, so most owners can't claim back the GST on our fee.

### Unit economics (founders' estimates, ₹10,000 rent)
| Item | ₹ per booking |
|---|---|
| Fee (exclusive of GST) | 3,000 |
| Payment fees (≈2% + GST on gross) | −84 |
| Field visit | −600 |
| Marketing (blended) | −500 |
| Tech | −15 |
| **Platform keeps** | **≈ 1,800** |

- At ₹1 lakh a month of fixed costs, break-even is about 56 bookings a month.
- Cheap triple-sharing beds barely pay for the visit, so start where rents run ₹10,000 and up: North Campus, Satya Niketan, Old Rajinder Nagar.

### Later revenue (not in v1)
- Owner software subscription, about ₹499 a month.
- Licensing help, ₹5,000–15,000 per owner.
- Commission of 10–15% on partner services (tiffin, laundry, movers).

### What we deliberately don't do
- Student fees. The first plan charged students ₹1,500 and kept only about ₹121 a booking.
- Room service inside other owners' PGs, which competes with the owner's own staff.
- Native iOS/Android apps in v1.

## 4. Dynamic pricing: what the founders mean

- The owner sets a **listed (base) rent** per room type. This is the normal, off-peak price.
- Prices can **rise** in peak season or at high occupancy and **fall** for early bookings, long stays or off-season move-ins.
- **100% of the rise goes to the owner.** Our fee is always 30% of the listed rent, so the platform earns the same whatever the dynamic price is.
- For us, dynamic pricing is **a tool that helps owners earn more**, which is why they list with us. It is not a revenue lever.
- In v1, owners and ops set pricing rules by hand. Automatic price suggestions come only after a full season of data.

### Guardrails (must be enforced in code)
1. **Price lock**: the monthly rent is fixed for the whole stay once booked.
2. **Rent bands**: Delhi's draft PG bill would have a Rent Regulation Committee set rent bands by area. Prices must stay inside a band once one is configured.
3. **Real scarcity only**: "Only 2 beds left" or "Price rises on 1 July" appear only when true, computed from live inventory and the actual rules.
4. **Full price upfront**: show the full monthly price, mandatory charges and deposit before booking. No drip pricing.
5. **Early-bird deals** are encouraged. They reward booking early instead of punishing late bookers.

### Integrity risk: gaming the listed rent
Because the fee is on the listed rent, an owner could set a low listed rent with large peak premiums to shrink our fee. For example, ₹6,000 listed rent with +60% in peak gives ₹9,600 rent but only a ₹1,800 fee. Guards:
- The listed rent must be the price actually charged when no rule applies.
- Total premium is capped. The default is +40%, configurable by admins.
- Ops get alerted when a listed rent is far below the locality median, or when the premium cap or rent band keeps clamping prices.

## 5. Trust design: why booking works the way it does

Students already take big risks: brokers ask for ₹10,000–12,000 advances to "arrange a room" and some disappear; listing photos often look nothing like the room; some owners keep deposits and want rent in cash with no receipt. The platform doesn't ask students to trust an unknown app. It makes paying through us **visibly safer** than paying an owner or broker directly, with very little money at risk.

- **Block, don't take.** Where the gateway allows, take the token as a UPI one-time mandate. The money stays blocked in the student's own bank account and is debited once after move-in. The bank releases it automatically if it's never debited, and the student can't cancel it on their own, so the owner still gets a firm booking. Fallback: take the token as a normal payment and hold it until move-in.
- **Money moves only after move-in + 24 hours.** The student gets a 24-hour window to check the room. If it isn't as shown, the token is released or refunded the same day and ops find them another verified bed.
- **Free cancellation** up to 7 days before move-in.
- **A trust ladder**: ask for more only as trust builds.
  1. Pay on the spot after a visit with our field agent (first season).
  2. Book from home: a live video tour by our staff, then a UPI block.
  3. First month's rent through the platform.
  4. Deposit help: a move-in photo report and mediation at move-out.
- **Protections apply only when paying through us**, as with Airbnb.
- **Look real**: our registered company name on the UPI screen (never a personal UPI ID), payments through an RBI-authorised gateway, a phone line a person answers, a help desk near campus from June to August, founders' names and faces, a verification report for every PG, and reviews only from students who actually stayed.
- **Borrow trust**: share the verification report and video tour with parents on WhatsApp and let parents pay; campus ambassadors who live in our PGs; owners telling students "book through them".

## 6. Leakage: the main business risk

Students gain nothing by skipping us because they pay no fee. Owners save our whole fee by dealing directly, so an owner might offer a student a discount to pay outside the platform. Next year's renewals and referrals can also skip us.

Product defences:
- **Owner agreement**: the fee is due for any student we introduced who moves in within 90 days, however they pay. Visit logs (timestamp, agent, GPS) prove the introduction. Agreement acceptance is recorded with version, timestamp and IP.
- **The token counts toward our fee.** At ₹10,000 rent the fee with GST is ₹3,540; the ₹2,000 token covers more than half, so if the rest of the rent goes straight to the owner we only invoice ₹1,540.

| Rest of first month's rent goes | We collect | Owner ends up with |
|---|---|---|
| Through our app (later) | ₹3,540, deducted automatically | ₹6,460 |
| Straight to the owner | ₹2,000 token + ₹1,540 invoice | ₹6,460 (gets ₹8,000, pays us ₹1,540) |

- **Contact details stay hidden** (owner phone, exact address) until a visit or booking is made through us. This is a config flag, pending legal review (see section 7).
- **Delisting**: owners who dodge the fee or break promises are removed.
- Later, monthly owner software keeps owners using the platform between bookings.

## 7. Regulation and compliance (get legal review before launch)

| Area | What applies | What the product does |
|---|---|---|
| Delhi PG bill (draft) | Licensing; area-wise rent bands considering occupancy, amenities, market rates and distance to colleges and transport ([Asianet Newsable, Sep 2026](https://newsable.asianetnews.com/india/delhi-govt-plans-new-policy-to-regulate-pgs-with-strict-safety-rules-articleshow-8sp2ph2)). On 8 Oct 2026 a high-powered committee said a portal mapping student PGs would launch soon and the draft would be finalised after Dussehra ([ANI via webindia123](https://news.webindia123.com/news/Articles/India/20261009/4508734.html)) | `rent_bands` table; licence status on every listing; list only licensed PGs once the registry is live |
| Building safety | A PG in Satya Niketan collapsed on 6 Sep 2026, killing seven people including five students; the MCD then surveyed 1,252 PG buildings ([The Logical Indian](https://thelogicalindian.com/delhi-satya-niketan-pg-rule-126801/)). Gurugram told tenants of unauthorised PGs to vacate by 30 Jun 2026 ([PropNewsTime](https://propnewstime.com/latestnewsstories/MzIyODA=/gurugram-cracks-down-on-illegal-pgs-tenants-asked-to-move-out-before-june-30-)) | Physical verification before publishing; a safety checklist; never list a flagged building |
| Dark patterns | CCPA's 2023 guidelines ban false urgency, drip pricing, basket sneaking, confirm-shaming and others; platforms were told in June 2025 to self-audit ([exchange4media](https://www.exchange4media.com/marketing-news/ccpa-gives-ecomm-players-3-months-to-root-out-dark-patterns-144202.html)) | Scarcity only from live data; full price upfront; no fake timers; dark-pattern audit before launch |
| E-commerce rules | Consumer Protection (E-Commerce) Rules 2020: a grievance officer whose details are visible on the site; acknowledge complaints within 48 hours and resolve within one month; show total price with a breakdown; marketplaces show seller details such as business name, address and customer care number ([IndiaLaw summary](https://www.indialaw.in/blog/consumer-protection-e-commerce-rules/)) | Grievance page and ticketing; price breakdown; **the seller-details duty conflicts with hiding owner contacts, so that flag needs legal advice** |
| Payments | Pooling owners' money can make us a payment aggregator, which RBI licenses ([Trilegal](https://trilegal.com/wp-content/uploads/2021/11/RBIs-Guidelines-on-Regulation-of-Payment-Aggregators-and-Payment-Gateways.pdf)). UPI payments to merchants above ₹2,000 carry a 0.4% fee from 15 Oct 2026 | Owner money moves only via gateway split settlement (Razorpay Route); tokens ≤ ₹2,000 |
| Personal data | DPDP Act 2023; DPDP Rules notified Nov 2025, with core duties applying from 13 May 2027; penalties up to ₹250 crore for weak security and ₹200 crore for not reporting a breach ([King Stubb & Kasiva](https://ksandk.com/data-protection-and-data-privacy/dpdp-compliance-for-startups-msmes/)) | Consent records, privacy notice, purpose limits, retention and deletion jobs, data export, breach runbook — all in v1 |
| Identity documents | Aadhaar numbers must not be collected or stored casually | Don't store Aadhaar numbers; if ID checks are needed, use DigiLocker-style verification or masked copies |
| SMS | Indian commercial SMS, including OTPs, needs DLT registration of sender ID and templates | Start DLT registration early; keep a WhatsApp OTP option |
| Payment gateway activation | Razorpay checks the site for About us, Contact us, Pricing, Terms, Privacy and Refund/Cancellation pages ([Razorpay docs](https://razorpay.com/docs/payments/dashboard/account-settings/business-website-details/)) | Build these pages before applying for live keys |
| GST | 18% on our fee; sequential invoice numbers per financial year | GST-ready invoices for owners |
| Noida societies | Many housing societies ban PGs | Record society permission during verification |

## 8. Go-to-market

- **Gate 1 (before building more)**: sign 30 owners in one micro-market to the 30% fee, and pre-book 50 students for July 2027. If busy-lane owners refuse, test 15–20% in peak months, or charging only off-season.
- **First micro-market**: North Campus or Satya Niketan per the plan, mapping every PG within 2 km. A campus where the founders have a network (for example NSUT) is also an option. Not decided yet.
- **Season one is visit-first**: students pay the token on the spot after a visit with our field agent.
- Expect refusals near North Campus, where owners have long paid brokers nothing because demand outruns supply. The paying owners are newer PGs, owners with off-season vacancies, owners with out-of-city students, and owners who need licensing help.

### Rent ranges for seed and test data (per bed per month, Jul 2026, [RealtyHunting](https://realtyhunting.com/pg-in-gurgaon-2026))
| City | Triple | Double | Single |
|---|---|---|---|
| Gurugram | ₹6,000–9,000 | ₹9,000–14,000 | ₹13,000–22,000 |
| Noida | ₹5,500–8,500 | ₹8,000–13,000 | ₹12,000–20,000 |

These are market observations, **not** official rent bands. Never seed them into `rent_bands` as official limits.

## 9. Open decisions — build as config, never pick silently

| Decision | Default in code until decided |
|---|---|
| Brand name | `YourBrand` placeholder in brand config |
| GST inclusive or exclusive | `exclusive` |
| Token amount | ₹2,000 |
| Late cancellation (< 7 days before move-in): who keeps the token | `refund_full` in v1, because paying a forfeited token to an owner needs Razorpay Route; `forfeit_to_owner` and `split` become available once Route is live |
| Hide owner phone and exact address until a visit | Hidden (flag `hide_owner_contact = true`), pending legal advice |
| Premium cap / discount cap | +40% / −30% |
| Price rounding step | ₹50 |
| UPI one-time mandate for tokens | Off until Razorpay enables it for our account |
| Free-cancellation cutoff / check window / hold time | 7 days / 24 hours / 15 minutes |
| Owner confirmation deadline | 12 hours, then auto-reject and refund |
| First micro-market | Seed data for North Campus and Satya Niketan |
| Map provider | Google Maps Platform behind an interface (see ARCHITECTURE.md) |

## 10. Glossary

- **PG**: paying-guest accommodation; a building with rooms rented out per bed, usually with meals.
- **Room type**: single, double, triple or quad sharing. **Bed**: the bookable unit.
- **Listed rent / base rent**: the owner's normal monthly rent for a bed of a room type. The fee is computed on this.
- **Dynamic rent**: the monthly rent after pricing rules for a given move-in date, stay length and occupancy.
- **Quote**: a server-computed, stored price offer for a bed, move-in date and stay length, valid for a short time.
- **Price lock**: the quote's monthly rent stays fixed for the whole booked stay.
- **Rent band**: a min/max rent for a locality and room type, official once Delhi notifies them.
- **Token**: the refundable amount that reserves a bed; counts toward the first month's rent.
- **Hold**: a short reservation of a bed while the student completes the token step.
- **Check window**: 24 hours after move-in for the student to confirm the room matches.
- **Placement fee**: 30% of one month's listed rent, paid once by the owner per tenant placed.
- **Leakage**: a deal we introduced that closes outside the platform.
- **Visit log**: the record of a visit (time, agent, GPS) that proves we introduced the student.
- **Verification report**: the field agent's safety and accuracy checklist for a PG.
