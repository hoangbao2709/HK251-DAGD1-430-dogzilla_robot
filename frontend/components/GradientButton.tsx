export default function GradientButton({ children, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className="cursor-pointer bg-gradient-to-r from-pink-500 to-purple-500 px-4 py-2 rounded-xl text-sm text-white shadow hover:opacity-90"
    >
      {children}
    </button>
  );
}
