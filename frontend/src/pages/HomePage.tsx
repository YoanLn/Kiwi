import { Link } from 'react-router-dom'
import { FileText, Upload, MessageCircle, CheckCircle } from 'lucide-react'
import Card from '../components/Card'
import Button from '../components/Button'

export default function HomePage() {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
      {/* Hero Section */}
      <div className="text-center mb-16">
        <h1 className="text-4xl font-bold text-gray-900 mb-4">
          Simplifiez vos declarations de sinistre
        </h1>
        <p className="text-xl text-gray-600 max-w-2xl mx-auto">
          Plateforme propulsee par l'IA pour gerer vos declarations de sinistre efficacement.
          Importez des documents, suivez le statut et obtenez de l'aide instantanement.
        </p>
        <div className="mt-8 flex justify-center gap-4">
          <Link to="/claims/new">
            <Button size="lg">Declarer un nouveau sinistre</Button>
          </Link>
          <Link to="/claims">
            <Button size="lg" variant="outline">Voir mes sinistres</Button>
          </Link>
        </div>
      </div>

      {/* Features */}
      <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6 mb-16">
        <Card>
          <FileText className="w-12 h-12 text-primary-600 mb-4" />
          <h3 className="text-lg font-semibold text-gray-900 mb-2">
            Declaration simple
          </h3>
          <p className="text-gray-600 text-sm">
            Declarez un sinistre en quelques minutes grace a notre parcours guide.
          </p>
        </Card>

        <Card>
          <Upload className="w-12 h-12 text-primary-600 mb-4" />
          <h3 className="text-lg font-semibold text-gray-900 mb-2">
            Verification des documents par IA
          </h3>
          <p className="text-gray-600 text-sm">
            Verification automatique de vos documents grace a une IA avancee.
          </p>
        </Card>

        <Card>
          <CheckCircle className="w-12 h-12 text-primary-600 mb-4" />
          <h3 className="text-lg font-semibold text-gray-900 mb-2">
            Suivi en temps reel
          </h3>
          <p className="text-gray-600 text-sm">
            Suivez le statut de votre sinistre et recevez des mises a jour a chaque etape.
          </p>
        </Card>

        <Card>
          <MessageCircle className="w-12 h-12 text-primary-600 mb-4" />
          <h3 className="text-lg font-semibold text-gray-900 mb-2">
            Assistant IA 24/7
          </h3>
          <p className="text-gray-600 text-sm">
            Obtenez des reponses instantanees a vos questions d'assurance a tout moment.
          </p>
        </Card>
      </div>

      {/* How It Works */}
      <div className="mb-16">
        <h2 className="text-3xl font-bold text-gray-900 text-center mb-12">
          Comment ca marche
        </h2>
        <div className="grid md:grid-cols-3 gap-8">
          <div className="text-center">
            <div className="w-16 h-16 bg-primary-100 text-primary-600 rounded-full flex items-center justify-center text-2xl font-bold mx-auto mb-4">
              1
            </div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">
              Declarez votre sinistre
            </h3>
            <p className="text-gray-600 text-sm">
              Fournissez les details du sinistre et importez les documents requis.
            </p>
          </div>

          <div className="text-center">
            <div className="w-16 h-16 bg-primary-100 text-primary-600 rounded-full flex items-center justify-center text-2xl font-bold mx-auto mb-4">
              2
            </div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">
              Verification par IA
            </h3>
            <p className="text-gray-600 text-sm">
              Notre IA verifie instantanement la completude de vos documents.
            </p>
          </div>

          <div className="text-center">
            <div className="w-16 h-16 bg-primary-100 text-primary-600 rounded-full flex items-center justify-center text-2xl font-bold mx-auto mb-4">
              3
            </div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">
              Obtenez l'approbation
            </h3>
            <p className="text-gray-600 text-sm">
              Suivez votre sinistre et recevez le paiement une fois approuve.
            </p>
          </div>
        </div>
      </div>

      {/* CTA */}
      <Card className="bg-primary-50 border-primary-200">
        <div className="text-center">
          <h2 className="text-2xl font-bold text-gray-900 mb-4">
            Besoin d'aide pour comprendre les termes d'assurance ?
          </h2>
          <p className="text-gray-600 mb-4">
            Discutez avec notre assistant IA pour obtenir des explications et des reponses instantanees.
          </p>
          <div className="flex items-center justify-center gap-2 text-primary-700">
            <MessageCircle className="w-5 h-5" />
            <p className="text-sm font-medium">
              Cliquez sur la bulle de chat en bas a droite pour commencer !
            </p>
          </div>
        </div>
      </Card>
    </div>
  )
}
