export default function TestModeBanner({ apiKeyConfigured = true }) {
  return (
    <div role="alert" className="bg-amber-400 px-4 py-2 text-center text-sm font-semibold text-amber-950">
      TEST MODE - use dummy data only. Never say real names, phone numbers, Aadhaar or any real beneficiary data.
      {!apiKeyConfigured && (
        <span className="ml-2 font-normal">
          (No SARVAM_API_KEY on the backend: live calls are off, Simulate still works.)
        </span>
      )}
    </div>
  );
}
