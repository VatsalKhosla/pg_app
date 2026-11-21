/**
 * The owners-and-PGs template (ADR 0072): its columns, with two rows of a fictional PG to copy.
 * One row per room type; the API's catalog/domain/listing_import.py reads it.
 */
const HEADER =
  "owner_name,owner_phone,pg_name,locality,address,gender,room_type,rent,deposit," +
  "owner_email,business_name,legal_name,latitude,longitude,meals,house_rules,amenities," +
  "description,room_label,ac,attached_bath,balcony";
const PG =
  'A Fictional Owner,98765 43210,Fictional Sample House,kamla-nagar,"House 1, a fictional lane",girls';
const DETAILS =
  "owner@example.com,,,28.6883,77.2102,three,No pets; Minimum stay: 11 months," +
  "wifi; hot-water; cctv,Rooms on two floors.,";
const TEMPLATE = [
  HEADER,
  `${PG},single,18000,18000,${DETAILS},yes,yes,no`,
  `${PG},double,12000,12000,${DETAILS},no,yes,no`,
].join("\n");

export function GET(): Response {
  return new Response(`${TEMPLATE}\n`, {
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": 'attachment; filename="listing-import-template.csv"',
    },
  });
}
