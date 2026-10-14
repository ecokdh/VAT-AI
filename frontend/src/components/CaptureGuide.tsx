export function CaptureGuide({seconds}: {seconds:number}) {
  return <section className="capture-guide" aria-label="첫 촬영 안내">
    <span className="eyebrow">처음 촬영하기 전에</span><h1 className="screen-title">이렇게 찍으면 더 잘 읽어요</h1>
    <svg viewBox="0 0 320 260" role="img" aria-label="어두운 바닥 위에 영수증 전체가 사각 가이드 안에 들어간 촬영 예시">
      <rect width="320" height="260" rx="24" fill="#25314a"/><rect x="57" y="17" width="206" height="225" rx="14" fill="none" stroke="#75a8ff" strokeWidth="3" strokeDasharray="12 8"/>
      <rect x="80" y="32" width="160" height="196" rx="4" fill="white"/>
      <text x="160" y="60" textAnchor="middle" fontSize="15" fill="#25314a" fontWeight="700">영수증 · 촬영 예시</text>
      {[85,105,125,145,165].map((y,i)=><g key={y}><rect x="97" y={y} width={i===0?90:65} height="5" rx="2" fill="#c4cede"/><rect x="191" y={y} width="30" height="5" rx="2" fill="#c4cede"/></g>)}
      <path d="M97 189h126" stroke="#c4cede"/><text x="99" y="211" fontSize="12" fill="#25314a">합계</text><text x="222" y="211" textAnchor="end" fontSize="12" fill="#25314a">11,000원</text>
    </svg>
    <ul><li>어두운 배경 위에 영수증을 평평하게 놓아주세요.</li><li>네 모서리와 모든 글자가 가이드 안에 들어오게 맞춰주세요.</li><li>그림자·빛 반사를 피하고 초점이 맞은 뒤 촬영해 주세요.</li></ul>
    <p role="status">{seconds}초 후 촬영 화면으로 이동합니다.</p><div className="guide-timer"><span/></div>
  </section>;
}
