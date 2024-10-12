<p align="center">
  <img src="https://user-images.githubusercontent.com/38581401/240117836-f06199ba-c80d-413a-9cb4-5adc76316bda.png" height="230" alt="MOSEC" />
</p>

<p align="center">
  <a href="https://discord.gg/Jq5vxuH69W">
    <img alt="lien d'invitation Discord" src="https://dcbadge.vercel.app/api/server/Jq5vxuH69W?style=flat">
  </a>
  <a href="https://pypi.org/project/mosec/">
    <img src="https://badge.fury.io/py/mosec.svg" alt="Version PyPI" height="20">
  </a>
  <a href="https://anaconda.org/conda-forge/mosec">
    <img src="https://anaconda.org/conda-forge/mosec/badges/version.svg" alt="conda-forge">
  </a>
  <a href="https://pypi.org/project/mosec">
    <img src="https://img.shields.io/pypi/pyversions/mosec" alt="Version Python" />
  </a>
  <a href="https://pepy.tech/project/mosec">
    <img src="https://static.pepy.tech/badge/mosec/month" alt="Téléchargements mensuels PyPi" height="20">
  </a>
  <a href="https://tldrlegal.com/license/apache-license-2.0-(apache-2.0)">
    <img src="https://img.shields.io/github/license/mosecorg/mosec" alt="Licence" height="20">
  </a>
  <a href="https://github.com/mosecorg/mosec/actions/workflows/check.yml?query=workflow%3A%22lint+and+test%22+branch%3Amain">
    <img src="https://github.com/mosecorg/mosec/actions/workflows/check.yml/badge.svg?branch=main" alt="Statut des vérifications" height="20">
  </a>
</p>

<p align="center">
  <i>Service de modèles efficace dans le Cloud.</i>
</p>

## Introduction

<p align="center">
  <img src="https://user-images.githubusercontent.com/38581401/234162688-efd74e46-4063-4624-ac32-b197e4d8e56b.png" height="230" alt="MOSEC" />
</p>

Mosec est un cadre de déploiement de modèles performant et flexible pour construire des microservices et des backends habilités par des modèles d'apprentissage automatique. Il comble l'écart entre les modèles que vous avez formés et un service API en ligne efficace.

- **Très performant** : couche web et coordination des tâches en Rust 🦀, offrant une grande rapidité avec une utilisation efficace du CPU grâce à l'I/O asynchrone.
- **Facilité d'utilisation** : interface utilisateur en Python 🐍, permettant de servir les modèles de manière indépendante de tout cadre ML, avec le même code que pour les tests hors ligne.
- **Regroupement dynamique** : agréger des demandes d'utilisateurs différents pour une inférence groupée et redistribuer les résultats.
- **Étages en pipeline** : plusieurs processus gèrent des charges de travail mixtes CPU/GPU/IO dans des étapes en pipeline.
- **Compatible avec le cloud** : conçu pour fonctionner dans le cloud, avec préchauffage de modèle, arrêt gracieux, et métriques de surveillance Prometheus, facilement géré par Kubernetes ou tout système d'orchestration de conteneurs.
- **Faire une chose bien** : se concentrer sur le déploiement en ligne, pour que les utilisateurs puissent optimiser leur modèle et la logique métier.

## Installation

Mosec nécessite Python 3.7 ou supérieur. Installez la dernière version du [package PyPI](https://pypi.org/project/mosec/) pour Linux x86_64 ou macOS x86_64/ARM64 avec :

```shell
pip install -U mosec
# ou installez avec conda
conda install conda-forge::mosec

```
Pour construire à partir du code source, installez [Rust](https://www.rust-lang.org/) et exécutez la commande suivante :

```shell
make package
```

Vous obtiendrez un fichier wheel Mosec dans le dossier dist.

Utilisation
Nous démontrons comment Mosec peut vous aider à héberger facilement un modèle stable de diffusion pré-entraîné en tant que service. Vous devez installer diffusers et transformers comme prérequis :
```
pip install --upgrade diffusers[torch] transformers
```
Écrire le serveur
<details> <summary>Cliquez ici pour voir le code du serveur avec des explications.</summary>
Tout d'abord, nous importons les bibliothèques et configurons un journal de base pour mieux observer ce qui se passe.

```
from io import BytesIO
from typing import List

import torch  # type: ignore
from diffusers import StableDiffusionPipeline  # type: ignore

from mosec import Server, Worker, get_logger
from mosec.mixin import MsgpackMixin

logger = get_logger()
```

Ensuite, nous **construisons une API** pour que les clients puissent interroger une invite textuelle et obtenir une image basée sur le modèle [stable-diffusion-v1-5](https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5) en seulement 3 étapes.

1) Définissez votre service comme une classe qui hérite de `mosec.Worker`. Ici, nous héritons également de `MsgpackMixin` pour utiliser le format de sérialisation [msgpack](https://msgpack.org/index.html)<sup>(a)</sup>.

2) Dans la méthode `__init__`, initialisez votre modèle et placez-le sur l'appareil correspondant. Vous pouvez éventuellement attribuer `self.example` avec des données pour réchauffer<sup>(b)</sup> le modèle. Notez que les données doivent être compatibles avec le format d'entrée de votre gestionnaire, que nous détaillons ci-dessous.

3) Remplacez la méthode `forward` pour écrire votre gestionnaire de service<sup>(c)</sup>, avec la signature `forward(self, data: Any | List[Any]) -> Any | List[Any]`. La réception ou le retour d'un seul élément ou d'un tuple dépend de la configuration ou non du [batching dynamique](#configuration)<sup>(d)</sup>.
```python
class StableDiffusion(MsgpackMixin, Worker):
    def __init__(self):
        self.pipe = StableDiffusionPipeline.from_pretrained(
            "sd-legacy/stable-diffusion-v1-5", torch_dtype=torch.float16
        )
        self.pipe.enable_model_cpu_offload()
        self.example = ["useless example prompt"] * 4  # warmup (batch_size=4)

    def forward(self, data: List[str]) -> List[memoryview]:
        logger.debug("generate images for %s", data)
        res = self.pipe(data)
        logger.debug("NSFW: %s", res[1])
        images = []
        for img in res[0]:
            dummy_file = BytesIO()
            img.save(dummy_file, format="JPEG")
            images.append(dummy_file.getbuffer())
        return images
```
> [!NOTE]
>
> (a) Dans cet exemple, nous retournons une image au format binaire, que JSON ne prend pas en charge (sauf s'il est encodé en base64, ce qui augmente la taille de la charge utile). Par conséquent, msgpack convient mieux à nos besoins. Si nous n'héritons pas de `MsgpackMixin`, JSON sera utilisé par défaut. En d'autres termes, le protocole de la requête/réponse du service peut être msgpack, JSON ou tout autre format (consultez nos [mixins](https://mosecorg.github.io/mosec/reference/interface.html#module-mosec.mixin)).
>
> (b) Le préchauffage aide généralement à allouer la mémoire GPU à l'avance. Si l'exemple de préchauffage est spécifié, le service ne sera prêt qu'après que l'exemple ait été transmis au gestionnaire. Cependant, si aucun exemple n'est donné, la latence de la première requête sera probablement plus longue. `example` doit être défini comme un élément unique ou un tuple en fonction de ce que `forward` attend de recevoir. De plus, dans le cas où vous souhaitez effectuer un préchauffage avec plusieurs exemples différents, vous pouvez définir `multi_examples` (démonstration [ici](https://mosecorg.github.io/mosec/examples/jax.html)).
>
> (c) Cet exemple montre un service à un seul étage, où le worker `StableDiffusion` prend directement la requête de l'utilisateur et répond avec une image. Ainsi, `forward` peut être considéré comme le gestionnaire de service complet. Cependant, nous pouvons également concevoir un service à plusieurs étages avec des workers effectuant différentes tâches (par exemple, téléchargement d'images, inférence du modèle, post-traitement) dans un pipeline. Dans ce cas, tout le pipeline est considéré comme le gestionnaire de service, avec le premier worker recevant la requête et le dernier envoyant la réponse. Le flux de données entre les workers est réalisé par communication inter-processus.
>
> (d) Étant donné que le regroupement dynamique est activé dans cet exemple, la méthode `forward` recevra idéalement une _liste_ de chaînes de caractères, par exemple, `['un chat mignon jouant avec une balle rouge', 'un homme assis devant un ordinateur', ...]`, agrégées à partir de différents clients pour une _inférence groupée_, améliorant ainsi le débit du système.

```python
if __name__ == "__main__":
    server = Server()
    # 1) `num` spécifie le nombre de processus qui seront lancés en parallèle.
    # 2) En configurant `max_batch_size` avec une valeur > 1, les données d'entrée dans votre
    # fonction `forward` seront une liste (batch); sinon, c'est un élément unique.
    server.append_worker(StableDiffusion, num=1, max_batch_size=4, max_wait_time=10)
    server.run()
```
</details>

### Exécuter le serveur

<details>
<summary>Cliquez ici pour voir comment exécuter et interroger le serveur.</summary>

Les extraits ci-dessus sont fusionnés dans notre fichier d'exemple. Vous pouvez directement l'exécuter à la racine du projet. Jetons d'abord un coup d'œil aux _arguments en ligne de commande_ (explications [ici](https://mosecorg.github.io/mosec/reference/arguments.html)) :

```shell
python examples/stable_diffusion/server.py --help
```
Ensuite, démarrons le serveur avec des journaux de débogage :

```
python examples/stable_diffusion/server.py --log-level debug --timeout 30000
```

Ouvrez http://127.0.0.1:8000/openapi/swagger/ dans votre navigateur pour obtenir la documentation OpenAPI.

Et dans un autre terminal, testez-le :

```
python examples/stable_diffusion/client.py --prompt "un mignon chat jouant avec une balle rouge" --output chat.jpg --port 8000
```
Vous obtiendrez une image nommée "chat.jpg" dans le répertoire courant.

Vous pouvez vérifier les métriques :
```
curl http://127.0.0.1:8000/metrics
```
Et voilà ! Vous venez d'héberger votre modèle stable-diffusion en tant que service ! 😉

</details> ```

## Exemples

Vous pouvez trouver plus d'exemples prêts à l'emploi dans la section [Exemple](https://mosecorg.github.io/mosec/examples/index.html). Elle inclut :

- [Pipeline](https://mosecorg.github.io/mosec/examples/echo.html) : une simple démo echo sans aucun modèle ML.
- [Validation des requêtes](https://mosecorg.github.io/mosec/examples/validate.html) : validez la requête avec une annotation de type.
- [Route multiple](https://mosecorg.github.io/mosec/examples/multi_route.html) : hébergez plusieurs modèles dans un seul service.
- [Service d'embedding](https://mosecorg.github.io/mosec/examples/embedding.html) : service d'embedding compatible avec OpenAI.
- [Service de reranking](https://mosecorg.github.io/mosec/examples/rerank.html) : réorganisez une liste de passages en fonction d'une requête.
- [IPC via mémoire partagée](https://mosecorg.github.io/mosec/examples/ipc.html) : communication inter-processus avec mémoire partagée.
- [Allocation de GPU personnalisée](https://mosecorg.github.io/mosec/examples/env.html) : déployez plusieurs répliques, chacune utilisant des GPU différents.
- [Métriques personnalisées](https://mosecorg.github.io/mosec/examples/metric.html) : enregistrez vos propres métriques pour la surveillance.
- [Inference Jax jittée](https://mosecorg.github.io/mosec/examples/jax.html) : la compilation just-in-time accélère l'inférence.
- Modèles de deep learning avec PyTorch :
  - [Analyse de sentiments](https://mosecorg.github.io/mosec/examples/pytorch.html#natural-language-processing) : inférer le sentiment d'une phrase.
  - [Reconnaissance d'image](https://mosecorg.github.io/mosec/examples/pytorch.html#computer-vision) : catégoriser une image donnée.
  - [Stable diffusion](https://mosecorg.github.io/mosec/examples/stable_diffusion.html) : générer des images à partir de textes, avec la sérialisation msgpack.


## Configuration

- **Batching dynamique**
  - Configurez `max_batch_size` et `max_wait_time` (en millisecondes) lorsque vous appelez `append_worker`.
  - Assurez-vous que l'inférence avec `max_batch_size` ne provoque pas de problèmes de mémoire sur le GPU.
  - En général, `max_wait_time` doit être inférieur au temps d'inférence du batch.
  - Si activé, le service collecte un lot lorsque soit le nombre de requêtes accumulées atteint `max_batch_size`, soit lorsque `max_wait_time` est écoulé. Cela est bénéfique lorsque le trafic est élevé.

Consultez la [documentation des arguments](https://mosecorg.github.io/mosec/reference/arguments.html) pour d'autres configurations.

## Déploiement

- Pour une image de base GPU avec `mosec` installé, consultez l'image officielle [`mosecorg/mosec`](https://hub.docker.com/r/mosecorg/mosec). Pour des cas d'utilisation plus complexes, envisagez d'utiliser [envd](https://github.com/tensorchord/envd).
- Ce service n'a pas besoin de Gunicorn ou NGINX, mais vous pouvez utiliser un contrôleur d'entrée si nécessaire.
- Le service doit être le processus PID 1 dans le conteneur car il gère plusieurs processus. Si vous devez exécuter plusieurs processus dans un conteneur, utilisez un superviseur comme [Supervisor](https://github.com/Supervisor/supervisor) ou [Horust](https://github.com/FedericoPonzi/Horust).
- **Métriques** à collecter :
  - `mosec_service_batch_size_bucket` : montre la distribution des tailles de batch.
  - `mosec_service_batch_duration_second_bucket` : montre la durée du batching dynamique pour chaque connexion à chaque étape (à partir de la réception de la première tâche).
  - `mosec_service_process_duration_second_bucket` : montre la durée de traitement pour chaque connexion à chaque étape (y compris le temps IPC, mais excluant la `mosec_service_batch_duration_second_bucket`).
  - `mosec_service_remaining_task` : montre le nombre de tâches en cours de traitement.
  - `mosec_service_throughput` : montre le débit du service.

## Optimisation des performances

- Trouvez les meilleures valeurs pour `max_batch_size` et `max_wait_time` pour votre service d'inférence. Les métriques montreront les histogrammes de la taille réelle des lots et de leur durée. Ces informations sont essentielles pour ajuster ces deux paramètres.
- Essayez de diviser tout le processus d'inférence en étapes CPU et GPU séparées (référence [DistilBERT](https://mosecorg.github.io/mosec/examples/pytorch.html#natural-language-processing)). Différentes étapes seront exécutées dans un [pipeline de données](https://fr.wikipedia.org/wiki/Pipeline_(informatique)), ce qui maintiendra le GPU occupé.
- Vous pouvez également ajuster le nombre de workers pour chaque étape. Par exemple, si votre pipeline se compose d'une étape CPU pour le prétraitement et d'une étape GPU pour l'inférence du modèle, augmenter le nombre de workers pour l'étape CPU peut aider à produire plus de données à traiter en batch pour l'étape d'inférence GPU. L'augmentation des workers de l'étape GPU peut maximiser l'utilisation de la mémoire et de la puissance de calcul du GPU. Les deux méthodes peuvent contribuer à une utilisation plus efficace du GPU, entraînant ainsi un débit de service plus élevé.
- Pour les services multi-étapes, notez que les données passant entre les différentes étapes seront sérialisées/désérialisées via les méthodes `serialize_ipc/deserialize_ipc`, donc des données extrêmement volumineuses pourraient ralentir tout le pipeline. Les données sérialisées sont transmises à l'étape suivante via Rust par défaut, mais vous pouvez activer la mémoire partagée pour réduire potentiellement la latence (référence [RedisShmIPCMixin](https://mosecorg.github.io/mosec/examples/ipc.html#redis-shm-ipc-py)).
- Choisissez des méthodes appropriées pour la sérialisation/désérialisation, utilisées pour décoder les requêtes utilisateur et encoder les réponses. Par défaut, les deux utilisent JSON. Cependant, les images et les embeddings ne sont pas bien pris en charge par JSON. Vous pouvez choisir msgpack, plus rapide et compatible avec les données binaires (référence [Stable Diffusion](https://mosecorg.github.io/mosec/examples/stable_diffusion.html)).
- Configurez les threads pour OpenBLAS ou MKL. Il se peut qu'ils ne choisissent pas les CPU les plus adaptés pour le processus Python en cours. Vous pouvez les configurer pour chaque worker en utilisant [env](https://mosecorg.github.io/mosec/reference/interface.html#mosec.server.Server.append_worker) (référence [allocation GPU personnalisée](https://mosecorg.github.io/mosec/examples/env.html)).
- Activez HTTP/2 côté client. `mosec` s'adapte automatiquement au protocole de l'utilisateur (par exemple, HTTP/2) depuis la version v0.8.8.


## Utilisateurs

Voici quelques entreprises et utilisateurs individuels qui utilisent Mosec :

- [Modelz](https://modelz.ai) : Plateforme serverless pour l'inférence ML.
- [MOSS](https://github.com/OpenLMLab/MOSS/blob/main/README_en.md) : Un modèle conversationnel open source similaire à ChatGPT.
- [TencentCloud](https://www.tencentcloud.com/document/product/1141/45261) : Plateforme de machine learning de Tencent Cloud, utilisant Mosec comme [cadre principal du serveur d'inférence](https://cloud.tencent.com/document/product/851/74148).
- [TensorChord](https://github.com/tensorchord) : Société d'infrastructure IA native du cloud.

## Citation

Si vous trouvez ce logiciel utile pour vos recherches, merci de bien vouloir le citer

```
@software{yang2021mosec,
  title = {{MOSEC: Model Serving made Efficient in the Cloud}},
  author = {Yang, Keming and Liu, Zichen and Cheng, Philip},
  url = {https://github.com/mosecorg/mosec},
  year = {2021}
}
```


## Contribuer

Nous acceptons toute forme de contribution. Vous pouvez nous donner votre avis en [créant des issues](https://github.com/mosecorg/mosec/issues/new/choose) ou en discutant sur [Discord](https://discord.gg/Jq5vxuH69W). Vous pouvez aussi directement [contribuer](https://mosecorg.github.io/mosec/development/contributing.html) en soumettant votre code et en faisant une pull request !

Pour commencer le développement, vous pouvez utiliser [envd](https://github.com/tensorchord/envd) pour créer un environnement isolé et propre en Python & Rust. Consultez la [documentation envd](https://envd.tensorchord.ai/) ou le fichier [build.envd](https://github.com/mosecorg/mosec/blob/main/build.envd) pour plus d'informations.
