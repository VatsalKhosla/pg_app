import "server-only";

import Image from "next/image";
import { getFormatter, getTranslations } from "next-intl/server";

import type { Visit } from "@/lib/ops/client";

/**
 * A submitted report as ops and the agent read it: the result, where and when it was made, every
 * answer, and the photos (private: their links are signed for five minutes).
 */
export async function VisitReport({ visit }: { visit: Visit }) {
  const t = await getTranslations("Field.summary");
  const tReport = await getTranslations("Field.report");
  const tOps = await getTranslations("Ops");
  const format = await getFormatter();
  const { checklist } = visit;
  if (checklist === null || visit.result === null || visit.submittedAt === null) return null;
  const yesNo = (answer: boolean) => (answer ? tReport("yes") : tReport("no"));

  const answers: [string, string][] = [
    [
      tReport("age"),
      checklist.buildingAgeYears === null
        ? t("unknown")
        : t("years", { years: checklist.buildingAgeYears }),
    ],
    [tReport("condition"), tReport(`conditions.${checklist.condition}`)],
    [tReport("cracks"), tReport(`crackOptions.${checklist.cracks}`)],
    [tReport("exits"), String(checklist.exits)],
    [tReport("extinguishers"), yesNo(checklist.fireExtinguishers)],
    [tReport("cctv"), yesNo(checklist.cctv)],
    [tReport("warden"), yesNo(checklist.warden)],
    [
      tReport("womenSafety"),
      checklist.womenSafety.length === 0
        ? t("none")
        : checklist.womenSafety
            .map((feature) => tReport(`womenSafetyOptions.${feature}`))
            .join(", "),
    ],
    [tReport("licenceNumber"), checklist.licenceNumber ?? t("noLicence")],
    [tReport("society"), tOps(`society.${checklist.societyPermission}`)],
    [tReport("authorityNotice"), yesNo(checklist.authorityNotice)],
  ];

  return (
    <div className="space-y-4">
      <p className="font-medium">
        {t(`results.${visit.result}`)}
        <span className="font-normal text-muted-foreground">
          {" · "}
          {t("submitted", {
            when: format.dateTime(new Date(visit.submittedAt), {
              dateStyle: "medium",
              timeStyle: "short",
            }),
          })}
          {visit.agent?.name ? ` · ${t("by", { name: visit.agent.name })}` : null}
        </span>
      </p>
      {visit.distanceM === null || visit.accuracyM === null ? null : (
        <p className="text-sm text-muted-foreground">
          {t("distance", { distance: visit.distanceM, accuracy: visit.accuracyM })}
        </p>
      )}
      <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[max-content_1fr]">
        {answers.map(([question, answer]) => (
          <div key={question} className="contents">
            <dt className="text-muted-foreground">{question}</dt>
            <dd>{answer}</dd>
          </div>
        ))}
      </dl>
      {visit.notes === "" ? null : (
        <div className="space-y-1 text-sm">
          <p className="text-muted-foreground">{tReport("notes")}</p>
          <p className="whitespace-pre-line">{visit.notes}</p>
        </div>
      )}
      {visit.photos.length === 0 ? null : (
        <ol className="grid grid-cols-3 gap-2 sm:grid-cols-6">
          {visit.photos.map((photo, index) => {
            const thumbnail = photo.renditions.find((rendition) => rendition.name === "thumb");
            return (
              <li
                key={photo.id}
                className="relative aspect-square overflow-hidden rounded bg-muted"
              >
                {thumbnail === undefined ? null : (
                  <Image
                    src={thumbnail.url}
                    alt={tReport("photo", { number: index + 1 })}
                    fill
                    unoptimized
                    sizes="160px"
                    className="object-cover"
                  />
                )}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
