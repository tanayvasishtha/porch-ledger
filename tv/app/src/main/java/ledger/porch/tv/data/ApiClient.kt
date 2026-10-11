package ledger.porch.tv.data

import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.request.HttpRequestBuilder
import io.ktor.client.request.get
import io.ktor.client.request.header
import io.ktor.client.request.parameter
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.client.statement.HttpResponse
import io.ktor.http.ContentType
import io.ktor.http.HttpHeaders
import io.ktor.http.HttpStatusCode
import io.ktor.http.contentType
import io.ktor.http.isSuccess
import ledger.porch.tv.BuildConfig
import ledger.porch.tv.data.dto.ClaimRequest
import ledger.porch.tv.data.dto.Problem
import ledger.porch.tv.data.dto.ResidentOut
import ledger.porch.tv.data.dto.VisitCard
import ledger.porch.tv.data.dto.VisitDetail
import ledger.porch.tv.data.dto.VisitList

class ApiException(
    val status: Int,
    val problem: Problem?,
) : Exception(
        problem?.detail?.ifEmpty { null } ?: "request failed with status $status",
    )

sealed interface VisitsResponse {
    data object NotModified : VisitsResponse

    data class Fresh(
        val body: VisitList,
        val etag: String,
    ) : VisitsResponse
}

class ApiClient(
    private val client: HttpClient,
    val baseUrl: String = BuildConfig.API_BASE_URL,
    private val houseKey: String = BuildConfig.HOUSE_KEY,
    private val houseId: String = "demo",
) {
    suspend fun visits(
        day: String?,
        etag: String?,
    ): VisitsResponse {
        val response =
            client.get("$baseUrl/v1/houses/$houseId/visits") {
                if (day != null) parameter("day", day)
                if (etag != null) header(HttpHeaders.IfNoneMatch, etag)
                auth()
            }
        if (response.status == HttpStatusCode.NotModified) return VisitsResponse.NotModified
        return VisitsResponse.Fresh(
            body = response.bodyOrProblem(),
            etag = response.headers[HttpHeaders.ETag] ?: error("200 without an ETag"),
        )
    }

    suspend fun detail(visitId: String): VisitDetail = client.get("$baseUrl/v1/visits/$visitId") { auth() }.bodyOrProblem()

    suspend fun claim(
        visitId: String,
        residentId: String,
    ): VisitCard =
        client
            .post("$baseUrl/v1/visits/$visitId/claim") {
                auth()
                contentType(ContentType.Application.Json)
                setBody(ClaimRequest(residentId))
            }.bodyOrProblem()

    suspend fun residents(): List<ResidentOut> = client.get("$baseUrl/v1/houses/$houseId/residents") { auth() }.bodyOrProblem()

    private suspend inline fun <reified T> HttpResponse.bodyOrProblem(): T {
        if (!status.isSuccess()) {
            val problem = runCatching { body<Problem>() }.getOrNull()
            throw ApiException(status.value, problem)
        }
        return body()
    }

    private fun HttpRequestBuilder.auth() {
        if (houseKey.isNotEmpty()) {
            header(HttpHeaders.Authorization, "Bearer $houseKey")
        }
    }
}
