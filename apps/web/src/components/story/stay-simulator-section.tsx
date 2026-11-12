import { getTranslations } from "next-intl/server";

import { StaySimulator } from "@/components/home/stay-simulator";
import { getPolicies } from "@/lib/api/public";
import { formatINR } from "@/lib/money";

const STEP_KEYS = ["find", "visit", "reserve", "moveIn"] as const;

/** The four steps in plain text: what the simulator starts from, and all there is without the API. */
export async function StepsList() {
  const t = await getTranslations("Home.steps");
  return (
    <ol className="grid max-w-3xl gap-6 sm:grid-cols-2">
      {STEP_KEYS.map((key) => (
        <li key={key}>
          <h3 className="text-title-3 font-medium">{t(`${key}.title`)}</h3>
          <p className="mt-1.5 leading-relaxed text-muted-foreground">{t(`${key}.body`)}</p>
        </li>
      ))}
    </ol>
  );
}

/** The stay simulator, with every word and figure read from the live policy on the server. */
export async function StaySimulatorSection() {
  let policies;
  try {
    policies = await getPolicies();
  } catch {
    return <StepsList />;
  }
  const [t, tSim, tToken, tBookings] = await Promise.all([
    getTranslations("Home.steps"),
    getTranslations("Home.sim"),
    getTranslations("TokenProtection"),
    getTranslations("Bookings.next"),
  ]);
  const { tokenPaise, freeCancelDays, checkWindowHours, confirmDeadlineHours } = policies.booking;
  return (
    <StaySimulator
      token={formatINR(tokenPaise)}
      stages={[
        { key: "find", title: t("find.title"), body: t("find.body"), place: 0 },
        { key: "visit", title: t("visit.title"), body: t("visit.body"), place: 0 },
        { key: "reserve", title: t("reserve.title"), body: t("reserve.body"), place: 1 },
        {
          key: "confirm",
          title: tSim("confirm"),
          body: tToken("confirm", { confirmHours: confirmDeadlineHours }),
          place: 1,
        },
        { key: "moveIn", title: t("moveIn.title"), body: t("moveIn.body"), place: 1 },
        {
          key: "check",
          title: tSim("check"),
          body: tToken("held", { checkHours: checkWindowHours }),
          place: 1,
        },
        { key: "settled", title: tSim("settled"), body: tBookings("active"), place: 2 },
      ]}
      branches={[
        {
          key: "cancel",
          stages: ["reserve", "confirm"],
          label: tSim("cancelLabel"),
          body: tToken("cancel", { freeCancelDays }),
        },
        {
          key: "ownerNo",
          stages: ["confirm"],
          label: tSim("ownerNoLabel"),
          body: tBookings("rejected"),
        },
        {
          key: "notAsShown",
          stages: ["check"],
          label: tSim("notAsShownLabel"),
          body: tToken("notAsShown", { checkHours: checkWindowHours }),
        },
      ]}
      text={{
        scrub: tSim("scrub"),
        step: tSim.raw("step") as string,
        places: [tSim("you"), tSim("held"), tSim("rent")],
        back: tSim("back"),
        play: tSim("play"),
        pause: tSim("pause"),
        happens: tSim("happens"),
        onTrack: tSim("onTrack"),
      }}
    />
  );
}
