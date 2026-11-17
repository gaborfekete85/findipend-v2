export default function BuyForm(_props: { portfolioId: number; onSaved: () => void }) {
  return (
    <form aria-label="Buy">
      <input aria-label="Total (USD)" />
      <input aria-label="Fee (USD)" />
      <input aria-label="Trade date" />
    </form>
  );
}
