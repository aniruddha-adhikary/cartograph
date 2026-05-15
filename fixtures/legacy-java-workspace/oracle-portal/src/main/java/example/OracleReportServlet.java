package example;

class OracleReportServlet {
  void render() {
    String sql = "SELECT * FROM REPORTS WHERE STATUS = ?";
  }
}
