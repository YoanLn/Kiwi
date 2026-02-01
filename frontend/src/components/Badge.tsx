import clsx from 'clsx'
import { ClaimStatus } from '../types'

interface BadgeProps {
  status: ClaimStatus
}

export default function Badge({ status }: BadgeProps) {
  const statusConfig = {
    [ClaimStatus.SUBMITTED]: {
      text: 'Soumis',
      className: 'bg-blue-100 text-blue-800',
    },
    [ClaimStatus.DOCUMENTS_PENDING]: {
      text: 'Documents en attente',
      className: 'bg-yellow-100 text-yellow-800',
    },
    [ClaimStatus.UNDER_REVIEW]: {
      text: "En cours d'examen",
      className: 'bg-purple-100 text-purple-800',
    },
    [ClaimStatus.ADDITIONAL_INFO_REQUIRED]: {
      text: 'Infos requises',
      className: 'bg-orange-100 text-orange-800',
    },
    [ClaimStatus.APPROVED]: {
      text: 'Approuve',
      className: 'bg-green-100 text-green-800',
    },
    [ClaimStatus.REJECTED]: {
      text: 'Rejete',
      className: 'bg-red-100 text-red-800',
    },
    [ClaimStatus.PAID]: {
      text: 'Paye',
      className: 'bg-emerald-100 text-emerald-800',
    },
  }

  const config = statusConfig[status]

  return (
    <span
      className={clsx(
        'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium',
        config.className
      )}
    >
      {config.text}
    </span>
  )
}
