import { useState } from 'react'

export default function ExportButton({ prompt, result }) {
  const [exporting, setExporting] = useState(false)

  async function handleExport() {
    setExporting(true)
    try {
      const { toPng } = await import('html-to-image')
      const { jsPDF } = await import('jspdf')

      const pdf = new jsPDF({ orientation: 'landscape', unit: 'mm', format: 'a4' })
      const pageW = pdf.internal.pageSize.getWidth()
      const pageH = pdf.internal.pageSize.getHeight()
      const primaryColor = [11, 102, 230]

      // Title Page / Overview Page
      pdf.setFontSize(18)
      pdf.setTextColor(...primaryColor)
      pdf.text('InsightFlow Professional Report', 20, 30)
      
      pdf.setFontSize(10)
      pdf.setTextColor(100, 116, 139)
      pdf.text(`Generated on: ${new Date().toLocaleString()}`, 20, 38)

      // Query Section
      pdf.setFontSize(12)
      pdf.setTextColor(15, 23, 42)
      pdf.setFont(undefined, 'bold')
      pdf.text('1. Business Query', 20, 55)
      pdf.setFontSize(11)
      pdf.setFont(undefined, 'normal')
      const queryLines = pdf.splitTextToSize(prompt || 'Dashboard Overview', pageW - 40)
      pdf.text(queryLines, 20, 65)

      let currentY = 65 + (queryLines.length * 6) + 15

      // Insight Section
      if (result && result.insight) {
        pdf.setFontSize(12)
        pdf.setFont(undefined, 'bold')
        pdf.text('2. Executive Insight', 20, currentY)
        pdf.setFontSize(11)
        pdf.setFont(undefined, 'normal')
        const insightLines = pdf.splitTextToSize(result.insight, pageW - 40)
        pdf.text(insightLines, 20, currentY + 10)
      }

      // Capture all Charts and put them on separate pages
      const chartElements = document.querySelectorAll('.chart-card')
      
      for (let i = 0; i < chartElements.length; i++) {
        pdf.addPage()
        
        // Page Header
        pdf.setFontSize(10)
        pdf.setTextColor(100, 116, 139)
        pdf.text(`InsightFlow Chart Visualization — ${i + 1}`, 15, 12)
        
        // Render Element using html-to-image
        const el = chartElements[i]
        const dataUrl = await toPng(el, {
          quality: 0.98,
          backgroundColor: '#ffffff',
          pixelRatio: 2,
        })
        
        const imgProps = pdf.getImageProperties(dataUrl)
        const usableH = pageH - 30
        const usableW = pageW - 30
        const ratio = Math.min(usableW / imgProps.width, usableH / imgProps.height)
        const imgW = imgProps.width * ratio
        const imgH = imgProps.height * ratio
        
        // Center the image horizontally & vertically below the header
        const xPos = (pageW - imgW) / 2
        const yPos = Math.max(20, (pageH - imgH) / 2)
        
        pdf.addImage(dataUrl, 'PNG', xPos, yPos, imgW, imgH)
      }

      pdf.save(`insightflow-report-${Date.now()}.pdf`)
    } catch (err) {
      alert('Export failed: ' + err.message)
    } finally {
      setExporting(false)
    }
  }

  return (
    <button className="btn btn-secondary btn-sm" onClick={handleExport} disabled={exporting}>
      {exporting ? '⏳ Generating PDF…' : '⬇ Export PDF Report'}
    </button>
  )
}
