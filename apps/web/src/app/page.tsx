import { brand } from "@/config/brand";

export default function HomePage() {
  return (
    <main>
      <h1>{brand.name}</h1>
      <p>{brand.tagline}</p>
    </main>
  );
}
